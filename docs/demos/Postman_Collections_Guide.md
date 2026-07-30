# Luminari Sage Postman Collections Guide

This guide explains how to use the Postman collections for the Luminari Sage API system.

## 📦 Available Collections

### 1. **Luminari GraphRAG Demo (Authenticated)**

- **File**: `Luminari_GraphRAG_Demo.postman_collection.json`
- **Purpose**: Demonstrates the hybrid Graph RAG system using MCP endpoints
- **Authentication**: Uses `SAGE_MCP_KEY` for MCP operations
- **Best for**: Understanding how the knowledge graph and RAG system work together

### 2. **Luminari Sage Chat Agent** ⭐

- **File**: `Luminari_Sage_Chat_Agent.postman_collection.json`
- **Purpose**: Interactive chat agent for natural lore exploration
- **Authentication**: Uses `SAGE_API_KEY` for API access
- **Best for**: Natural conversation about lore, testing the chat system

## 🔐 Authentication Setup

### API Keys

You'll need these API keys from your system administrator:

```
SAGE_API_KEY = your-sage-api-key-here
SAGE_MCP_KEY = your-sage-mcp-key-here
```

**To configure after importing:**

1. Edit each collection in Postman
2. Go to Variables tab
3. Update `SAGE_API_KEY` and `SAGE_MCP_KEY` values
4. Save the collection

### Authentication Method

Both collections use **API Key authentication** with:

- **Header**: `X-API-Key`
- **Value**: `{{SAGE_API_KEY}}` or `{{SAGE_MCP_KEY}}`
- **Location**: Header

## 🚀 Getting Started

### Option 1: Import Collections into Postman

1. **Open Postman**
2. **Import Collections**:
   - Click "Import" in Postman
   - Drag & drop both `.json` files
   - Or click "Upload Files" and select them

3. **Configure API Keys**:
   - Edit each collection → Variables tab
   - Set `SAGE_API_KEY` and `SAGE_MCP_KEY` to your actual keys
   - Base URL is pre-set to `https://luminarimud.com/sage`

### Option 2: Manual Setup

If you prefer to set up manually:

1. **Create Environment** in Postman with:

   ```
   SAGE_API_KEY = your-sage-api-key-here
   SAGE_MCP_KEY = your-sage-mcp-key-here
   base_url = https://luminarimud.com/sage
   ```

2. **Add Authentication** to collection:
   - Type: API Key
   - Header: `X-API-Key`
   - Value: `{{SAGE_API_KEY}}` (for chat) or `{{SAGE_MCP_KEY}}` (for GraphRAG)

## 💬 Chat Agent Collection Usage

### Basic Workflow

1. **🏥 Health Check** - Verify API is running
2. **💬 Start Chat Conversation** - Begin new conversation
3. **📖 Ask About Specific Lore** - Continue the conversation
4. **📋 List Conversations** - See conversation history
5. **🗑️ Delete Conversation** - Clean up when done

### Auto-Variable Setting

The chat collection automatically captures:

- `conversation_id` - Current conversation
- `stream_id` - Streaming session ID

These are used in subsequent requests to maintain conversation context.

### Example Chat Flow

```javascript
// 1. Start conversation
POST /api/v1/chat/message
{
  "message": "Tell me about Paladine",
  "user_id": "demo_user"
}
// → Returns conversation_id, stream_id

// 2. Continue conversation
POST /api/v1/chat/message
{
  "message": "What about his relationships with other gods?",
  "conversation_id": "{{conversation_id}}", // Auto-populated
  "user_id": "demo_user"
}

// 3. Get full conversation history
GET /api/v1/chat/conversations/{{conversation_id}}
```

## 📊 GraphRAG Collection Usage

### MCP Tool Calls

The GraphRAG collection demonstrates MCP (Model Context Protocol) tools:

1. **query_lore** - Hybrid RAG queries
2. **search_entities** - Find specific entities
3. **get_entity_details** - Deep entity information
4. **get_entity_relationships** - Relationship mapping
5. **get_lore_stats** - System statistics

### Example GraphRAG Flow

```javascript
// 1. Query lore with RAG
POST /mcp/tools/call
{
  "name": "query_lore",
  "arguments": {
    "query": "What is Void's Wake?",
    "max_results": 4
  }
}

// 2. Find specific entities
POST /mcp/tools/call
{
  "name": "search_entities",
  "arguments": {
    "query": "Void Witch",
    "limit": 5
  }
}

// 3. Get detailed entity info
POST /mcp/tools/call
{
  "name": "get_entity_details",
  "arguments": {
    "entity_id": "stable_entity_id_here"
  }
}
```

## 🔧 Health Checks

Use `/ping` for basic liveness and `/api/v1/health` for dependency status.
Authentication-introspection endpoints are intentionally not exposed.

## 💡 Tips & Best Practices

### Chat Agent Tips

- **Be specific**: Ask detailed questions for better responses
- **Use context**: Reference previous conversation topics
- **Try different intents**: Ask for stories, comparisons, or facts
- **Manage conversations**: Delete old conversations to keep things tidy

### GraphRAG Tips

- **Start broad**: Use `query_lore` for general questions
- **Drill down**: Use entity search and details for specifics
- **Follow relationships**: Use relationship endpoints to explore connections
- **Check stats**: Use stats endpoint to understand data scope

### Authentication Tips

- **Check health first**: Always verify API is accessible
- **Test debug endpoints**: Use auth debug endpoints if having issues
- **Watch for 401 errors**: Invalid/missing API keys return clear error messages
- **Use HTTPS**: All requests must use `https://luminarimud.com/sage`

## 🆘 Troubleshooting

### Common Issues

1. **401 Unauthorized**
   - Check API key is correct
   - Verify `X-API-Key` header is set
   - Use correct key type (API vs MCP)

2. **404 Not Found**
   - Check base URL is `https://luminarimud.com/sage`
   - Verify endpoint path is correct
   - Ensure API is deployed

3. **Empty Responses**
   - Normal for some queries if no matching data
   - Try different search terms
   - Check system stats for data availability

4. **Conversation Issues**
   - Verify conversation_id is captured from first message
   - Check user_id is consistent across requests
   - Use conversation history to debug state

### Debug Steps

1. Run **Health Check** to verify connectivity
2. Run **Debug: Auth Env** to check authentication
3. Try **System Statistics** to verify data availability
4. Check Postman Console for detailed error messages

## 📝 Collection Features

### Smart Variables

- Auto-capture conversation and stream IDs
- Environment-based configuration
- Reusable authentication setup

### Rich Examples

- Realistic lore queries and conversations
- Multiple conversation intents (story, comparison, exploration)
- Comprehensive endpoint coverage

### Documentation

- Detailed request descriptions
- Parameter explanations
- Expected response formats

---

**Happy exploring the world of Luminari! 🗺️⚔️🏰**

_For technical support or questions about the API, check the Swagger documentation at `https://luminarimud.com/sage/docs`_
