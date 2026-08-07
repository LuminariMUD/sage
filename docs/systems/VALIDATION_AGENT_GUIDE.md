# Validation Agent Testing Guide

**Version**: 0.7.15
**Last Updated**: 2025-11-12  
**Status**: Production Ready

This guide walks you through testing the `relationship_validator_v1_llm` agent using Postman to validate knowledge graph relationships and manage human review workflows. For comprehensive system documentation, see [VALIDATION_SYSTEM.md](VALIDATION_SYSTEM.md).

## 🚀 **Quick Start**

1. **Import Postman Collection**: `Luminari_Validation_Agent_Demo.postman_collection.json`
2. **Set Environment Variable**: `base_url = https://luminarimud.com/sage`
3. **Run System Health Check** (folder 1)
4. **Trigger Validation** (folder 2)
5. **Review Results** (folders 3-5)

## 📋 **Collection Overview**

### **1. System Health** 
- ✅ API Health Check
- 📊 Get System Statistics

### **2. Run Validation**
- 🔍 **Full Relationship Validation** - Complete analysis with all checks
- ⚡ **Quick Validation** - Small sample for testing
- 🔗 **Bidirectional Check Only** - Focus on missing reverse relationships

### **3. Review Results**
- 📚 Get Validation History
- 📄 Get Specific Validation Report  
- 📈 Get Validation Statistics

### **4. Human Review Workflow**
- 👀 Get All Unreviewed Findings
- ⚠️ Get Critical/Error Findings Only
- 🔗 Get Bidirectional Issues
- 📊 Get Validation Statistics

### **5. Mark Findings as Reviewed**
- ✅ Review Finding - Fixed
- ❌ Review Finding - False Positive  
- 📝 Review Finding - Acknowledged
- 🚫 Review Finding - Won't Fix
- 🔍 Review Finding - Needs Investigation

### **6. Autonomous Corrections (Optional)**
- 🤖 Run Validation with Auto-Corrections
- 📋 Preview Corrections (Dry-Run)
- ♻️ Rollback Single Correction
- ♻️ Rollback Entire Batch
- 📈 Get Correction Statistics

### **7. Test Scenarios**
- 📄 New Data Validation
- 🚀 Pre-Release Check
- 🐛 Debug Specific Issue
- 🤖 Autonomous Correction Workflow

## 🔧 **Key Parameters**

### **Validation Configuration:**
```json
{
  "entity_limit": 1000,           // Max entities to analyze
  "relationship_limit": 5000,     // Max relationships to check  
  "check_bidirectional": true,    // Missing reverse relationships
  "check_mutual_exclusivity": true, // Contradictory relationships
  "check_hierarchies": true,      // Command/serve consistency
  "check_semantic_consistency": true // Property validation
}
```

### **Filtering Options:**
- **Severity**: `critical`, `error`, `warning`, `info`
- **Categories**: `bidirectional_consistency`, `mutual_exclusivity`, `hierarchical_consistency`, `semantic_consistency`, `entity_connectivity`, `duplicate_relationships`, `semantic_appropriateness`, `llm_graphrag_analysis`
- **Agent ID**: `relationship_validator_v1_llm`

### **Autonomous Correction Parameters:**
```json
{
  "auto_correct": true,              // Enable autonomous corrections
  "correct_duplicates": true,        // Remove duplicate relationships
  "standardize_semantics": true,     // Standardize semantic types
  "confidence_threshold": 0.85,      // Min confidence for corrections
  "max_corrections": 100,            // Limit corrections per run
  "dry_run": true                    // Preview only (true = safe)
}
```

## 🎯 **Testing Workflow**

### **Step 1: Health Check**
```
GET /api/v1/health
GET /api/v1/stats
```
**Expected**: 200 OK with system status

### **Step 2: Run Validation**
```
POST /api/v1/validate/relationships
```
**Expected**: 
- Report ID stored in environment
- Findings count and severity breakdown
- Execution time logged

### **Step 3: Review Results** 
```
GET /api/v1/validate/history
GET /api/v1/validate/report/{{last_report_id}}
```
**Expected**:
- List of validation reports
- Detailed findings with confidence scores
- Markdown report for human review

### **Step 4: Filter High-Priority Items**
```
GET /api/v1/validate/findings/unreviewed?severity=error
```
**Expected**:
- Critical issues requiring immediate attention
- Evidence and affected entities listed

### **Step 5: Mark as Reviewed**
```
POST /api/v1/validate/findings/{{finding_id}}/review
{
  "reviewer": "admin",
  "action": "fixed", 
  "notes": "Added missing bidirectional relationship"
}
```
**Expected**: 200 OK with confirmation message

## 🔍 **What the Agent Detects**

### **Bidirectional Consistency** (`check_bidirectional: true`)
**Finds**: Missing reverse relationships
```
Example: Paladine "allied_with" Kiri-Jolith 
Missing: Kiri-Jolith "allied_with" Paladine
```

### **Mutual Exclusivity** (`check_mutual_exclusivity: true`)  
**Finds**: Contradictory relationships
```
Example: Same entities have both "allied_with" AND "opposed_to"
```

### **Hierarchical Consistency** (`check_hierarchies: true`)
**Finds**: Missing inverse hierarchical relationships
```
Example: Astinus "commands" Aesthetics
Missing: Aesthetics "serves_under" Astinus
```

### **Semantic Consistency** (`check_semantic_consistency: true`)
**Finds**: 
- Relationships missing semantic type information
- Inconsistent property formatting
- RELATES_TO/MENTIONS edges without meaning

### **Additional Checks**
- **Orphaned Entities**: Entities with no relationships
- **Duplicate Relationships**: Same relationship defined multiple times

## 📊 **Understanding Results**

### **Confidence Scores**
- **0.9-1.0**: Very high confidence (logical contradictions)
- **0.7-0.8**: High confidence (strong evidence patterns)
- **0.5-0.6**: Medium confidence (possible issues)
- **0.3-0.4**: Low confidence (speculation) 
- **0.1-0.2**: Very low confidence (weak signals)

### **Severity Levels**
- **Critical**: Data corruption, major inconsistencies
- **Error**: Clear logical problems needing fixes
- **Warning**: Potential issues worth investigating
- **Info**: Suggestions for improvement

### **Review Actions**
- **fixed**: Issue has been resolved
- **false_positive**: Agent was wrong, no issue exists
- **acknowledged**: Valid finding, will fix later
- **wont_fix**: Issue exists but intentional
- **needs_investigation**: Requires further analysis

## 🧪 **Testing Scenarios**

### **Scenario 1: Post-Ingestion Validation**
After adding new lore documents:
```json
{
  "entity_limit": 500,
  "relationship_limit": 2000,
  "check_bidirectional": true,
  "check_mutual_exclusivity": true,
  "check_hierarchies": true,
  "check_semantic_consistency": true,
  "enable_llm_analysis": true
}
```

### **Scenario 2: Pre-Release Quality Check**
Before major deployments:
```json
{
  "entity_limit": 2000,
  "relationship_limit": 10000,
  "check_bidirectional": true,
  "check_mutual_exclusivity": true,
  "check_hierarchies": true,
  "check_semantic_consistency": true,
  "enable_llm_analysis": true
}
```

### **Scenario 3: Debug Specific Issues**
When investigating reported problems:
```json
{
  "entity_limit": 100,
  "relationship_limit": 300,
  "check_bidirectional": false,
  "check_mutual_exclusivity": true,  // Focus on one check
  "check_hierarchies": false,
  "check_semantic_consistency": false,
  "enable_llm_analysis": false  // Faster for debugging
}
```

### **Scenario 4: Autonomous Correction Workflow**

**Step 1: Preview Corrections (Dry-Run)**
```json
{
  "entity_limit": 1000,
  "relationship_limit": 5000,
  "check_bidirectional": true,
  "check_mutual_exclusivity": true,
  "check_hierarchies": true,
  "check_semantic_consistency": true,
  "auto_correct": true,
  "correct_duplicates": true,
  "standardize_semantics": true,
  "dry_run": true  // SAFE MODE - preview only
}
```

**Expected Response:**
```json
{
  "report_id": "uuid",
  "findings_count": 45,
  "metadata": {
    "auto_correction_enabled": true,
    "corrections_applied": 23,
    "correction_batch_id": "batch-uuid",
    "duplicates_removed": 15,
    "semantics_standardized": 8,
    "dry_run": true  // Confirms preview mode
  }
}
```

**Step 2: Review Proposed Corrections**
Review the findings to see what would be corrected:
```bash
GET /api/v1/validate/report/{report_id}
```

**Step 3: Apply Corrections (Live)**
If satisfied with preview, run again with `dry_run: false`:
```json
{
  "entity_limit": 1000,
  "relationship_limit": 5000,
  "auto_correct": true,
  "dry_run": false  // ACTUALLY APPLY CHANGES
}
```

**Step 4: Monitor Corrections**
```bash
GET /api/v1/corrections/history?limit=50
GET /api/v1/corrections/batch/{batch_id}/summary
```

**Step 5: Rollback if Needed**
Preview rollback first:
```bash
GET /api/v1/corrections/batch/{batch_id}/preview
```

Then rollback if necessary:
```bash
POST /api/v1/corrections/batch/{batch_id}/rollback
{
  "rollback_by": "admin",
  "rollback_reason": "Correction logic needs adjustment"
}
```

## 📝 **Environment Variables**

The collection automatically manages these variables:
- `base_url`: API endpoint
- `last_report_id`: Most recent validation report
- `last_agent_id`: Agent that ran the validation
- `sample_finding_id`: Sample finding for testing review
- `unreviewed_finding_id`: First unreviewed finding

## ⚠️ **Important Notes**

1. **Agent Labeling**: All findings are tagged with `relationship_validator_v1` for human review
2. **Automatic Storage**: All validation results are stored in PostgreSQL for audit trails
3. **No Automatic Changes**: Agent only suggests, never modifies data automatically
4. **Human Review Required**: All findings should be reviewed before taking action
5. **Confidence Interpretation**: Lower confidence findings may require human judgment

## 🔧 **Troubleshooting**

### **Common Issues:**

#### **1. 500 Error on Validation**
**Symptoms**: API returns 500 Internal Server Error

**Possible Causes**:
- OpenAI API key missing or invalid
- OpenAI API rate limit exceeded
- Neo4j connection timeout
- PostgreSQL connection issues

**Solutions**:
```bash
# Check API key is set
curl https://luminarimud.com/sage/api/v1/health -H "X-API-Key: YOUR_KEY"

# Try without LLM analysis
{
  "enable_llm_analysis": false  // Skip LLM to isolate issue
}

# Check logs
docker logs luminari-api --tail=100
```

#### **2. Empty or No Results**
**Symptoms**: Validation returns 0 findings on known problematic data

**Possible Causes**:
- Entity/relationship limits too small
- Validation checks disabled
- Data doesn't match validation rules
- Database not connected

**Solutions**:
```bash
# Check what's being validated
GET /api/v1/stats  # See if data exists

# Increase limits
{
  "entity_limit": 2000,
  "relationship_limit": 10000
}

# Ensure checks are enabled
{
  "check_bidirectional": true,
  "check_mutual_exclusivity": true,
  "check_hierarchies": true,
  "check_semantic_consistency": true
}
```

#### **3. Timeout on Large Datasets**
**Symptoms**: Validation times out or takes too long

**Solutions**:
```json
// Option 1: Reduce limits
{
  "entity_limit": 500,
  "relationship_limit": 2000,
  "enable_llm_analysis": false  // Much faster
}

// Option 2: Disable expensive checks
{
  "check_bidirectional": false,  // Disable if not needed
  "enable_llm_analysis": false   // LLM analysis is slowest
}

// Option 3: Batch processing
// Run multiple smaller validations
```

#### **4. 404 on Report**
**Symptoms**: Cannot retrieve validation report

**Possible Causes**:
- Report ID typo
- Report not yet stored (async operation)
- PostgreSQL storage failed

**Solutions**:
```bash
# List recent reports
GET /api/v1/validate/history

# Check report ID is correct (UUID format)

# Verify storage is working
GET /api/v1/validate/stats
```

#### **5. Corrections Not Applied**
**Symptoms**: Ran with `auto_correct: true` but nothing changed

**Possible Causes**:
- `dry_run: true` (preview mode)
- Confidence threshold too high
- No correctable issues found
- Correction limit reached

**Solutions**:
```json
// Verify dry_run is false
{
  "auto_correct": true,
  "dry_run": false  // Must be false to apply
}

// Lower confidence threshold
{
  "confidence_threshold": 0.80  // Default is 0.85
}

// Check what was analyzed
// Review report metadata
```

#### **6. Rollback Failed**
**Symptoms**: Rollback returns error or doesn't restore data

**Possible Causes**:
- Correction already rolled back
- Neo4j nodes deleted manually
- Insufficient permissions

**Solutions**:
```bash
# Check if already rolled back
GET /api/v1/corrections/{correction_id}
# Look for "rolled_back": true

# Preview before rolling back
GET /api/v1/corrections/batch/{batch_id}/preview

# Check Neo4j connection
# Check correction storage exists
GET /api/v1/corrections/history
```

### **Performance Tips:**
- **Start Small**: 100 entities, 500 relationships for initial testing
- **Disable LLM**: Set `enable_llm_analysis: false` for faster validation
- **Specific Checks**: Enable only needed validation types for debugging
- **Batch Processing**: Split large graphs into multiple validation runs
- **Filter Results**: Use severity filters to focus on high-priority issues
- **Monitor Stats**: Use `/api/v1/validate/stats` to track performance over time

### **Best Practices:**
1. **Always Preview First**: Use `dry_run: true` before applying corrections
2. **Review Findings**: Check validation report before acting on findings
3. **Start Conservative**: Begin with high confidence threshold (0.85+)
4. **Test on Subset**: Run on small data sample before full validation
5. **Monitor Rollbacks**: High rollback rate indicates adjustment needed
6. **Document Reviews**: Use review notes to track decision rationale
7. **Regular Validation**: Schedule regular validations for ongoing monitoring

## 📈 **Next Steps**

1. **Run Full Validation** to establish baseline data quality
2. **Review High-Priority Findings** (critical/error severity with high confidence)
3. **Mark Findings as Reviewed** to track progress and build audit trail
4. **Test Autonomous Corrections** with dry-run mode first
5. **Monitor Statistics** over time to identify patterns
6. **Schedule Regular Validations** based on data update frequency
7. **Document Rollback Reasons** to improve correction logic

The validation system is designed to work with human review, so the more you mark findings as reviewed with appropriate actions and rollback reasons, the better you can tune the confidence thresholds and correction logic.

---

## 📚 **Related Documentation**

- **[VALIDATION_SYSTEM.md](VALIDATION_SYSTEM.md)**: Comprehensive validation architecture and implementation details
- **[CORRECTION_SYSTEM.md](CORRECTION_SYSTEM.md)**: Complete correction and rollback system documentation
- **[API_REFERENCE.md](API_REFERENCE.md)**: Full API endpoint reference with examples
- **[AGENT_SYSTEM.md](AGENT_SYSTEM.md)**: Overview of all agent systems including validation agents
- **[DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md)**: Developer integration and debugging guide

---

**Version**: 0.7.15
**Last Updated**: 2025-11-12  
**Status**: Production Ready
