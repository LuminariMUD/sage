# ReAct Streaming Implementation Plan

## Overview
Implement streaming of the ReAct agent's thinking process to provide real-time feedback to users, similar to Claude's dimmed thinking text, making the wait feel shorter and providing transparency into the generation process.

## Architecture Design

### 1. Backend Changes - Streaming from ReAct Agent

**Modify `SimpleQuestlineReActAgent` to yield streaming events:**
- Create a `stream_questline_generation` async generator method
- Yield events for each step: Thought, Action, Observation
- Event types:
  - `react_thought`: The agent's reasoning
  - `react_action`: What tool is being called
  - `react_observation`: Result of the tool call
  - `quest_generated`: When a quest is complete
  - `questline_complete`: Final result

**Update `generate_questline` tool in `modern_service.py`:**
- Check if client supports streaming
- If yes, use streaming version and yield events
- Pass events through the existing SSE streaming infrastructure

### 2. Event Structure
```python
{
    "type": "react_thought",
    "content": "I need to search for lore about the Mark of the Luminari...",
    "step": 1,
    "quest_number": null
}
{
    "type": "react_action", 
    "content": "search_lore",
    "args": {"query": "Mark of the Luminari", "limit": 10},
    "step": 2
}
{
    "type": "react_observation",
    "content": "Found 15 relevant lore entries about the Mark...",
    "step": 3
}
```

### 3. Frontend UI Changes

**Add new UI components in `chat-ui.html`:**
- Create a collapsible "thinking" section with dimmed text
- Style it with:
  - Semi-transparent background
  - Smaller, italicized font
  - Indented from main content
  - Collapse/expand toggle button
  - Auto-collapse when generation completes

**CSS additions:**
```css
.react-thinking {
    background: rgba(0, 0, 0, 0.05);
    border-left: 3px solid rgba(74, 144, 226, 0.3);
    padding: 10px;
    margin: 10px 0;
    font-size: 0.9em;
    font-style: italic;
    color: rgba(44, 62, 80, 0.7);
}

.react-thinking.collapsed {
    max-height: 40px;
    overflow: hidden;
}

.react-thinking-toggle {
    cursor: pointer;
    color: var(--primary-color);
    font-size: 0.8em;
}
```

**JavaScript event handlers:**
- Listen for `react_*` events in the SSE stream
- Append thinking text to a dedicated container
- Update in real-time as events arrive
- Auto-collapse when `questline_complete` received

### 4. Implementation Steps

1. **Create streaming version of ReAct agent:**
   - New method `stream_questline_generation` in `questline_react_simple.py`
   - Yield events at each reasoning step
   - Maintain same logic but with streaming output

2. **Update modern service:**
   - Detect if in streaming context
   - Call streaming version when appropriate
   - Pass through ReAct events to SSE stream

3. **Enhance UI:**
   - Add thinking container to chat interface
   - Style with CSS for dimmed/collapsible display
   - Handle new event types in JavaScript

4. **Add toggle controls:**
   - Button to expand/collapse thinking
   - Settings option to show/hide thinking by default
   - Smooth animations for expand/collapse

## Benefits
- **Transparency**: Users see the reasoning process
- **Engagement**: Makes wait time feel shorter
- **Debugging**: Easier to see where issues occur
- **Trust**: Users understand how the system works
- **UX**: Collapsible design keeps interface clean

## Example User Experience
1. User requests: "Create a questline about the Mark of the Luminari"
2. Thinking section appears with dimmed text:
   - *"Thinking: I need to search for lore about the Mark..."*
   - *"Searching: Mark of the Luminari, Luminari heroes..."*
   - *"Found: 15 relevant entries including..."*
   - *"Thinking: For quest 1, I'll introduce the concept..."*
   - *"Generating: Quest 1 - The First Signs..."*
3. As each quest completes, it appears in the main chat
4. When done, thinking section auto-collapses with option to review

## Code Examples

### Backend Streaming Generator
```python
async def stream_questline_generation(self, premise: str, num_quests: int):
    """Stream ReAct thinking process."""
    
    # Yield thinking
    yield {
        "type": "react_thought",
        "content": f"I need to search for lore about {premise}",
        "step": 1
    }
    
    # Yield action
    yield {
        "type": "react_action",
        "content": "search_lore",
        "args": {"query": premise},
        "step": 2
    }
    
    # Execute and yield observation
    results = await search_lore(premise)
    yield {
        "type": "react_observation",
        "content": f"Found {len(results)} relevant entries",
        "step": 3
    }
    
    # Continue for each quest...
```

### Frontend Handler
```javascript
function handleReActEvent(event) {
    const thinkingContainer = document.getElementById('react-thinking');
    
    switch(event.type) {
        case 'react_thought':
            appendThought(event.content);
            break;
        case 'react_action':
            appendAction(event.content, event.args);
            break;
        case 'react_observation':
            appendObservation(event.content);
            break;
        case 'questline_complete':
            collapseThinking();
            break;
    }
}
```

## Future Enhancements
- Add settings for verbosity level
- Allow filtering of certain event types
- Export thinking trace for debugging
- Add progress indicators for long operations
- Support for nested thinking (sub-thoughts)

## Implementation Priority
1. Backend streaming infrastructure (High)
2. Basic UI display of thoughts (High)
3. Collapsible UI with styling (Medium)
4. Settings and customization (Low)
5. Advanced features (Low)