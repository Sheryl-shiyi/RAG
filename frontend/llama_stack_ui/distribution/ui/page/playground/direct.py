# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the terms described in the LICENSE file in
# the root directory of this source tree.

"""
Direct mode implementation for chat with manual RAG.
"""

import logging
import traceback

import streamlit as st

from llama_stack_ui.distribution.ui.modules.api import llama_stack_api
from llama_stack_ui.distribution.ui.modules.utils import clean_text, get_vector_db_name, run_input_shields, run_output_shields


logger = logging.getLogger(__name__)


# ============================================================================
# Direct Mode - Helper Functions
# ============================================================================

def extract_text_from_search_result(result):
    """Extract and clean text content from a search result object."""
    text = None

    # Handle Data objects with content list
    if hasattr(result, 'content') and isinstance(result.content, list):
        for content_item in result.content:
            if hasattr(content_item, 'text'):
                text = content_item.text
                break

    # Handle simple content attribute
    elif hasattr(result, 'content') and isinstance(result.content, str):
        text = result.content

    # Handle dict format
    elif isinstance(result, dict) and 'content' in result:
        if isinstance(result['content'], list) and result['content']:
            text = result['content'][0].get('text', '')
        else:
            text = result['content']

    return clean_text(text) if text else None


def search_vector_store_direct(prompt, vector_db_id, vector_db_name, top_k, state):
    """Search vector store and extract context for Direct mode."""
    context_parts = []
    display_results = []

    # Show search status
    with state.containers.tool_status:
        st.markdown(f"🛠 :grey[_Searching vector store: {vector_db_name}_]")

    logger.debug("Searching vector store %s with query: %s", vector_db_id, prompt)

    # Call vector store search API
    search_response = llama_stack_api.client.vector_stores.search(
        vector_store_id=vector_db_id,
        query=prompt,
        max_num_results=top_k,
    )

    logger.debug("Search response: %s", search_response)

    # Extract search results from response
    search_results = []

    if hasattr(search_response, 'data') and search_response.data:
        search_results = search_response.data
    elif hasattr(search_response, 'chunks') and search_response.chunks:
        search_results = search_response.chunks
    elif hasattr(search_response, 'results') and search_response.results:
        search_results = search_response.results

    # Display and process search results
    if search_results:
        # Build context and display data from search results
        for result in search_results:
            text_content = extract_text_from_search_result(result)
            if text_content:
                attrs = getattr(result, 'attributes', {})
                source = attrs.get('source') or getattr(result, 'filename', 'unknown')
                context_parts.append(f"[Source: {source}]: {text_content}")
                display_results.append({"source": source, "text": text_content})

        state.tool_results.append({
            'title': f"📄 File Search Results from '{vector_db_name}'",
            'type': 'json',
            'content': display_results
        })
        with state.containers.tool_results:
            with st.expander(f"📄 File Search Results from '{vector_db_name}'", expanded=False):
                st.json(display_results)

        logger.debug("Built context with %s documents", len(context_parts))
    else:
        # No results found
        with state.containers.tool_results:
            st.info(f"No results found in '{vector_db_name}'")

    return search_results, context_parts, display_results


def build_rag_messages(prompt, context_parts, system_prompt):
    """Build messages for LLM - with or without RAG context."""
    if context_parts:
        # RAG mode: Format user message with explicit CONTEXT and QUERY sections
        context = "\n\n".join(context_parts)
        extended_prompt = (
            f"Please answer the following query using the context below.\n\n"
            f"CONTEXT:\n{context}\n\n"
            f"QUERY:\n{prompt}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": extended_prompt}
        ]
        logger.debug(
            "Built RAG prompt with %s documents, total context length: %s",
            len(context_parts), len(context)
        )
    else:
        # Normal chat mode: no context
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        logger.debug("No context - using normal chat mode")

    return messages


def stream_completions_direct(completion_response, state):
    """Stream chunks from Completions API and update state."""
    for chunk in completion_response:
        logger.debug("Completion chunk: %s", chunk)
        if hasattr(chunk, 'choices') and chunk.choices:
            delta = chunk.choices[0].delta

            # Handle reasoning content (for models that support it like R1)
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                state.update_reasoning(delta.reasoning_content)

            # Handle regular content
            if hasattr(delta, 'content') and delta.content:
                state.update_message(delta.content)


def save_direct_response_to_session(state, all_search_results):
    """Save direct response to session state."""
    if state.guardrail_blocked:
        response_dict = {
            "role": "assistant",
            "content": f"🛡️ {state.guardrail_blocked}",
            "guardrail_blocked": state.guardrail_blocked,
            "stop_reason": "end_of_message",
        }
        st.session_state.messages.append(response_dict)
        return

    state.finalize_reasoning()
    state.finalize_message()

    response_dict = {
        "role": "assistant",
        "content": state.full_response,
        "stop_reason": "end_of_message"
    }

    # Save reasoning if present
    if state.reasoning_text:
        response_dict["reasoning"] = state.reasoning_text

    # Save search results for history display if we had any
    if all_search_results:
        db_names = [name for name, _ in all_search_results]
        response_dict["tool_results"] = [
            {
                'title': f'📄 File Search Results from \'{name}\'',
                'type': 'json',
                'content': display
            }
            for name, display in all_search_results
        ]
        response_dict["tool_status"] = (
            f"🛠 :grey[_Searched vector stores: {', '.join(db_names)}_]"
        )

    st.session_state.messages.append(response_dict)


# ============================================================================
# Direct Mode - Main Function
# ============================================================================

def _get_live_shields(config):
    """Read guardrail selections directly from widget state to avoid stale config."""
    input_shields = st.session_state.get("guardrail_input_selector", config.guardrails.input_shields)
    output_shields = st.session_state.get("guardrail_output_selector", config.guardrails.output_shields)
    return input_shields or [], output_shields or []


def direct_process_prompt(prompt, state, config):
    """Direct mode: Manual RAG with completions API."""
    input_shields, output_shields = _get_live_shields(config)
    context_parts = []
    all_search_results = []

    vector_dbs = st.session_state.get("direct_vector_dbs", [])
    if not vector_dbs:
        logger.debug("No vector DB selected - normal chat mode")

    try:
        # Step 0: Run input guardrails
        if input_shields:
            guardrail_status = state.containers.tool_status.empty()
            guardrail_status.markdown("🛡️ :grey[_Running input guardrail check..._]")
            is_blocked, violation_msg, blocked_shield = run_input_shields(
                llama_stack_api.client, input_shields, prompt
            )
            if is_blocked:
                guardrail_status.empty()
                blocked_msg = f"**Input Guardrail Triggered** (`{blocked_shield}`): {violation_msg}"
                st.warning(blocked_msg, icon="🛡️")
                state.guardrail_blocked = blocked_msg
                state.full_response = ""
                save_direct_response_to_session(state, [])
                return
            guardrail_status.empty()

        # Step 1: Search each selected vector store (renders results immediately)
        for vector_db in vector_dbs:
            vector_db_id = vector_db.id
            vector_db_name = get_vector_db_name(vector_db)
            search_results, parts, display = search_vector_store_direct(
                prompt, vector_db_id, vector_db_name, config.sampling.top_k, state
            )
            if search_results:
                all_search_results.append((vector_db_name, display))
            context_parts.extend(parts)

        # Update tool status to final state
        if all_search_results:
            db_names = [name for name, _ in all_search_results]
            status_msg = f"🛠 :grey[_Searched vector stores: {', '.join(db_names)}_]"
            state.tool_status = status_msg

        # Step 2: Build messages (with or without RAG context)
        messages = build_rag_messages(prompt, context_parts, config.system_prompt)

        # Step 3: Call completions API
        logger.debug("Calling completions API with %s messages", len(messages))
        for i, msg in enumerate(messages):
            logger.debug("  Message %s (%s): %s...", i, msg['role'], msg['content'][:200])

        state.show_thinking()
        completion_response = llama_stack_api.client.chat.completions.create(
            model=config.model,
            messages=messages,
            temperature=config.sampling.temperature,
            max_tokens=config.sampling.max_tokens,
            stream=True,
        )

        # Step 4: Stream response and update UI
        stream_completions_direct(completion_response, state)

        # Step 5: Run output guardrails
        if output_shields and state.full_response:
            guardrail_status = state.containers.tool_status.empty()
            guardrail_status.markdown("🛡️ :grey[_Running output guardrail check..._]")
            is_blocked, violation_msg, blocked_shield = run_output_shields(
                llama_stack_api.client, output_shields, prompt, state.full_response
            )
            guardrail_status.empty()
            if is_blocked:
                blocked_msg = f"**Output Guardrail Triggered** (`{blocked_shield}`): {violation_msg}"
                state.containers.clear_tools()
                state.containers.message.empty()
                st.warning(blocked_msg, icon="🛡️")
                state.guardrail_blocked = blocked_msg
                state.full_response = ""
                save_direct_response_to_session(state, [])
                return

        # Step 6: Save to session
        save_direct_response_to_session(state, all_search_results)

    except Exception as e:
        st.error(f"Error in Direct mode: {str(e)}")
        logger.debug("Direct mode error: %s", e)
        logger.debug("%s", traceback.format_exc())
