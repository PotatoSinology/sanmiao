# Implementation Plan: Validating Dynasty/Ruler/Era Combinations

## Problem Statement

Currently, sanmiao tags dynasties, rulers, and eras separately for performance reasons. However, this approach creates false positives where invalid combinations (e.g., a Tang dynasty name with a Wei dynasty era name) are tagged as belonging to the same date.

### Current Flow
1. **Tagging Phase**: Separate regex patterns tag `<dyn>`, `<ruler>`, and `<era>` elements independently
2. **Consolidation Phase**: `consolidate_date()` merges adjacent date elements without validation
3. **Candidate Generation**: `bulk_generate_date_candidates()` filters invalid combinations, but only after they've been created

### Example False Positive
```
Text: "唐太和"
Tagged: <date><dyn>唐</dyn></date><date><era>太和</era></date>
Consolidated: <date><dyn>唐</dyn><era>太和</era></date>
Problem: 太和 is a Wei dynasty era, not Tang!
```

## Solution Approach

**Enhanced Solution 2**: Keep separate tagging for coverage, but add validation during consolidation and post-consolidation cleanup.

### Benefits
- ✅ Preserves coverage (won't miss dates due to missing alternative names)
- ✅ Prevents false positives by validating combinations
- ✅ Maintains performance (validation only when merging)
- ✅ Can be implemented incrementally

## Implementation Steps

### Phase 1: Create Validation Helper Functions

**File**: `src/sanmiao/tagging.py`

**New Functions**:

1. **`validate_dyn_era_combination(dyn_str, era_str, era_df)`**
   - Check if an era belongs to a dynasty
   - Parameters:
     - `dyn_str`: str, dynasty name from XML
     - `era_str`: str, era name from XML
     - `era_df`: DataFrame, era table with columns `era_name`, `dyn_id`
   - Returns: `bool` (True if valid combination exists)
   - Logic: Look up era in era_df, check if its dyn_id matches any dynasty with dyn_str

2. **`validate_dyn_ruler_combination(dyn_str, ruler_str, ruler_df, dyn_tag_df)`**
   - Check if a ruler belongs to a dynasty
   - Parameters:
     - `dyn_str`: str, dynasty name from XML
     - `ruler_str`: str, ruler name from XML
     - `ruler_df`: DataFrame, ruler table with `person_id`, `dyn_id`
     - `dyn_tag_df`: DataFrame, dynasty tags with `string`, `dyn_id`
   - Returns: `bool` (True if valid combination exists)
   - Logic: Resolve both to IDs, check if ruler's dyn_id matches dynasty's dyn_id

3. **`validate_ruler_era_combination(ruler_str, era_str, era_df, ruler_tag_df)`**
   - Check if an era belongs to a ruler
   - Parameters:
     - `ruler_str`: str, ruler name from XML
     - `era_str`: str, era name from XML
     - `era_df`: DataFrame, era table with `era_name`, `ruler_id`
     - `ruler_tag_df`: DataFrame, ruler tags with `string`, `person_id`
   - Returns: `bool` (True if valid combination exists)
   - Logic: Resolve both to IDs, check if era's ruler_id matches ruler's person_id

4. **`validate_date_combination(date_element, era_df, ruler_df, dyn_tag_df, ruler_tag_df)`**
   - Main validation function for a consolidated date element
   - Parameters:
     - `date_element`: et.Element, XML date element
     - `era_df`, `ruler_df`, `dyn_tag_df`, `ruler_tag_df`: DataFrames
   - Returns: `bool` (True if all combinations in date are valid)
   - Logic:
     - Extract dyn_str, ruler_str, era_str from date element
     - If multiple context tags present, validate all pairwise combinations
     - Return False if any combination is invalid

**Implementation Notes**:
- These functions need access to the data tables
- Consider caching lookups for performance
- Handle cases where strings don't match any IDs (return False for validation)

### Phase 2: Modify Consolidation with Validation

**File**: `src/sanmiao/tagging.py`

**Function to Modify**: `consolidate_date(text)`

**Approach**: Add validation before merging adjacent date elements

**Changes**:
1. Parse XML to get element tree
2. Before each merge operation in the consolidation list, check if the combination would be valid
3. Only merge if validation passes
4. If validation fails, keep elements separate (they'll be filtered out later)

**Modified Logic**:
```python
# For each merge pair (e.g., 'dyn' -> 'era')
# Before: text = re.sub(rf'</{tup[0]}></date>，*<date><{tup[1]}', ...)
# After: 
#   1. Find all instances of pattern
#   2. For each instance, extract the two date elements
#   3. Validate the combination
#   4. Only merge if valid
```

**Alternative Approach** (Simpler):
- Keep current consolidation logic
- Add post-consolidation validation step (see Phase 3)

### Phase 3: Post-Consolidation Validation and Cleanup

**File**: `src/sanmiao/tagging.py`

**New Function**: `validate_and_clean_consolidated_dates(xml_root, era_df, ruler_df, dyn_tag_df, ruler_tag_df, civ=None)`

**Purpose**: After consolidation, validate all date elements and remove invalid context tags

**Logic**:
1. Iterate through all `<date>` elements in XML
2. For each date, check if it has multiple context tags (dyn+ruler, dyn+era, ruler+era, or all three)
3. If multiple context tags present:
   - Extract strings from each tag
   - Validate all pairwise combinations
   - If any combination is invalid:
     - Remove the least specific tag(s) (dynasty < ruler < era in specificity)
     - Or remove all context tags if no valid combination exists
4. Return modified XML root

**Specific Rules**:
- If `dyn` + `era` present and invalid: remove `dyn` (era is more specific)
- If `dyn` + `ruler` present and invalid: remove `dyn` (ruler is more specific)
- If `ruler` + `era` present and invalid: remove `ruler` (era is more specific)
- If all three present and invalid: keep only the most specific valid combination

**Integration Point**: 
- Call this function in `tag_date_elements()` after `consolidate_date()` but before returning

### Phase 4: Update `tag_date_elements()` Function

**File**: `src/sanmiao/tagging.py`

**Function to Modify**: `tag_date_elements(text, civ=None)`

**Changes**:
1. Load data tables early (currently loaded for filtering, but need them for validation)
2. After `consolidate_date()` call, add validation step:
   ```python
   # After consolidation
   xml_root = et.fromstring(xml_string)
   xml_root = validate_and_clean_consolidated_dates(
       xml_root, era_tag_df, dyn_tag_df, ruler_tag_df, 
       era_df, ruler_df, civ=civ
   )
   xml_string = et.tostring(xml_root, encoding='utf8').decode('utf8')
   ```

**Note**: Need to load full tables (not just tag tables) for validation:
- `era_df` (not just `era_tag_df`)
- `ruler_df` (not just `ruler_tag_df`)
- `dyn_df` (for part_of relationships)

### Phase 5: Handle Edge Cases

**Edge Cases to Consider**:

1. **Missing Alternative Names**
   - If a dynasty/ruler/era name isn't in the tag tables, validation should fail gracefully
   - Don't remove tags if we can't validate (conservative approach)

2. **Part-of Relationships**
   - When validating dynasty+era, check part_of relationships
   - If "Later Tang" is part_of "Tang", and era belongs to "Tang", it's valid

3. **Multiple Matches**
   - If a string matches multiple IDs, check if ANY combination is valid
   - If at least one is valid, keep the tags

4. **Standalone Tags**
   - Dates with only one context tag (e.g., just `<dyn>`) don't need validation
   - Only validate when multiple context tags are present

5. **Performance**
   - Cache lookups to avoid repeated DataFrame queries
   - Consider pre-building lookup dictionaries for common validations

## Testing Strategy

### Test Cases

1. **Valid Combinations**
   - "唐太和" (Tang dynasty + valid Tang era) → Should consolidate and keep both
   - "魏太和" (Wei dynasty + valid Wei era) → Should consolidate and keep both

2. **Invalid Combinations**
   - "唐太和" where 太和 is Wei era → Should remove dynasty tag or keep separate
   - "魏开元" where 开元 is Tang era → Should remove dynasty tag or keep separate

3. **Multiple Context Tags**
   - Date with dyn+ruler+era where only ruler+era is valid → Remove dyn
   - Date with dyn+ruler+era where none are valid → Remove all context tags

4. **Edge Cases**
   - Missing alternative names → Conservative: keep tags if can't validate
   - Part-of relationships → Should validate correctly
   - Standalone tags → Should not be affected

### Test Data
- Create test XML strings with various combinations
- Test with real historical data to ensure no false negatives

## Implementation Order

1. ✅ **Phase 1**: Create validation helper functions
2. ✅ **Phase 2**: Implement post-consolidation validation (simpler than modifying consolidation)
3. ✅ **Phase 3**: Integrate into `tag_date_elements()`
4. ✅ **Phase 4**: Test with real data
5. ✅ **Phase 5**: Optimize performance if needed

## Alternative: Validation in Candidate Generation

**Note**: We could also add more aggressive filtering in `bulk_generate_date_candidates()`, but this would be less efficient since invalid combinations would still be created and then filtered out. The approach above prevents invalid combinations from being created in the first place.

## Future Enhancements

1. **Confidence Scoring**: Instead of binary valid/invalid, score combinations by confidence
2. **Context-Aware Validation**: Use surrounding text to help disambiguate
3. **Learning from Corrections**: Track false positives and improve validation rules

## Files to Modify

1. `src/sanmiao/tagging.py`
   - Add validation helper functions
   - Add `validate_and_clean_consolidated_dates()` function
   - Modify `tag_date_elements()` to call validation

2. `src/sanmiao/loaders.py` (if needed)
   - May need to expose table loading for validation functions

## Dependencies

- No new external dependencies required
- Uses existing pandas, lxml, and data tables
