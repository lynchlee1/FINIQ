## Behavior Classification Rules
### 1. Purpose
- This document explains how to categorise and describe system behavior using consistent criteria.
- Carefully check the conditions and functions of system behavior to make sure that same behavior doesn't get classified differently across documents.
<br>

Every operation must be able to answer the following three questions:
1. Does it affect the resulting data, or is it the way the UI · API execute?
2. Does it operate under the right conditions, or does it operate after an unexpected failure?
3. Which state transition does it directly control: accepting input, producing a candidate result, or validating and certifying a completed result?

### 2. Rules
- Keep each rule focused on one functionality.
- Each operation is classified according to the following order: **Layer → Behavior → Responsibility**.

#### 2.1 Layer: Core · Serving
- **Layer** separates the rules that produce results and the rules that display them to the user.
- **Core** takes input and produces results. 
  - This category includes rules that determine which values should be selected or excluded.
  - If the results produced from the same input differ, it is classified as 'Core'. 
- **Serving** determines how the UI and API execute the Core and display its progress and results.
  - It does not affect the results produced by the Core.
  - If the results are the same, but the method of requesting or displaying them is different, then it's Serving.
- Within both the Core and Serving categories, behavior should be classified as Feature, Fallback, or Shutdown.

#### 2.2 Behavior: Feature · Fallback · Shutdown
- **Behavior** distinguishes between normal conditions and how failures are handled.
  - First, determine whether it is a feature.
  - Only when it is not a feature, distinguish between fallback and shutdown.
- **Feature** is a set of rules for processing normal input and data.
  - It includes selecting or rejecting values.
  - It includes normal operations creating empty results.
- **Fallback** uses a different value or method, or reduces the processing scope, to continue after an unexpected failure.
- **Shutdown** is a set of rules for when an unexpected failure occurs and it is not possible to produce a safe result, resulting in the current execution ending.

```text
Does it work with normal input and data?
├── Yes: Feature
└── No
    ├── Continue using a different method or with a reduced scope: Fallback
    └── Terminated because a safe result could not be produced: Shutdown
```

- Do not classify it simply because certain items were excluded or because execution was terminated.
  - If processing follows the normal rules, it is a Feature.
  - It is only classified as a Fallback if an unexpected failure occurs and the current execution continues, or as a Shutdown if it is terminated.

#### 2.3 Responsibility: Input Handling · Core Processing · Result Validation
- **Responsibility** identifies the state transition directly controlled by a rule within the current operation.
  - Before assigning a responsibility, define the current operation's external input, intended business result, and publication boundary. A file that was a result of an earlier operation can be an input to the current operation.
- **Input Handling** turns an external request, source file, stored state, or prior result into accepted input for the current operation.
  - It includes reading, locating, parsing, normalising, and checking the availability, type, format, schema, and required values of input before business-result production begins.
  - It does not include extracting domain values or selecting values that will become fields of the intended result.
- **Core Processing** turns accepted input into the intended candidate result.
  - It includes domain extraction, selection, exclusion, calculation, transformation, aggregation, linking, ordering, result-structure construction, and persistence of business-result values.
  - A check performed while the candidate result is incomplete is Core Processing when it determines or changes what the result contains.
- **Result Validation** examines a completed candidate result and determines whether it may be published, saved as valid, returned, or reused.
  - It includes checking the completed result's structure, completeness, counts, and internal or source consistency.
  - It includes creating validation evidence such as a manifest, validation metadata, warning record, or completion marker when that evidence certifies the completed result without producing or changing its business values.
  - If a rule repairs, substitutes, recalculates, filters, or otherwise changes business-result values, it is not Result Validation.

```text
External data
└── accept as executable input? ── Input Handling
    └── produce or change business-result values? ── Core Processing
        └── candidate result complete
            └── approve, reject, or certify it without changing business values? ── Result Validation
```

### 3. Boundary Rules
- Core and Serving are distinguished by whether the rule changes the result produced by the Core.
  - A rule that changes the result produced by the Core is Core.
  - A rule that only changes how the result is requested or displayed is Serving.
- Feature and Fallback are distinguished by whether the alternative is part of normal processing.
  - Selecting a value according to a predefined order is a Feature.
  - Using another value because the intended value failed is a Fallback.
- Feature and Shutdown are distinguished by why the execution ends.
  - Rejecting valid input according to a normal rule is a Feature.
  - Ending execution because of an unexpected failure is a Shutdown.
- Validation and its failure handling must be written as separate rules.
  - A validation performed during normal processing is a Feature.
  - Continuing with a reduced result after validation fails is a Fallback.
  - Ending execution after validation fails is a Shutdown.
- Excluding an item does not determine the classification by itself.
  - Excluding an item according to a normal rule is a Feature.
  - Excluding a failed item and continuing with the remaining items is a Fallback.
- Responsibility is determined by the role of the data in the current operation, not by the file name or its role in a previous operation.
  - Validating a prior saved result before reusing it as the current input is Input Handling.
  - Validating a newly completed candidate immediately before publication is Result Validation.
- Creating a file does not determine the responsibility by itself.
  - Creating or changing business-result values is Core Processing.
  - Creating a manifest, validation metadata, warning record, or completion marker that certifies an unchanged completed result is Result Validation.
- The words `read`, `check`, `validate`, `save`, `metadata`, and `result` do not determine responsibility. Apply the state-transition test instead.
- A rule must not span more than one responsibility transition.
  - Split input acceptance, result production, and completed-result validation into separate rules.
  - In particular, do not combine validation failure detection, user confirmation, and alternative result production in one rule.
- For every rule, its description should make the boundary observable: name the accepted input, the business result or candidate being acted on, and whether the candidate is incomplete or complete at that point.

### 4. Writing Example
The following example shows every combination of Layer, Behavior, and Responsibility. An actual document should include only the rules that exist and mark an empty category explicitly (`없음` in the disclosure documents).

```markdown
### Core

#### Feature

**[Input Handling] Date Range Validation**
- Accepts a start date that is earlier than or equal to the end date.

**[Core Processing] Record Filtering**
- Selects records that match the accepted date range.

**[Result Validation] Result Certification Metadata**
- After all records have been selected, confirms that the reported count matches the records and writes a completion marker without changing them.

#### Fallback

**[Input Handling] Compatible Input Format**
- Uses a supported legacy input format when the current format cannot be read.

**[Core Processing] Failed Record Exclusion**
- Excludes a record that cannot be processed and continues with the remaining records.

**[Result Validation] Alternate Result Certification**
- Uses an independent consistency check when the primary completed-result check cannot run, without changing the candidate result.

#### Shutdown

**[Input Handling] Unreadable Input Rejection**
- Stops before processing when a required input file cannot be read.

**[Core Processing] Processing Failure Termination**
- Stops when processing fails before a complete result can be produced.

**[Result Validation] Invalid Result Rejection**
- Stops the operation without saving when the reported count does not match the result.

### Serving

#### Feature

**[Input Handling] Request Parameter Conversion**
- Converts request parameters into the input format accepted by the Core.

**[Core Processing] Task Execution**
- Starts the Core operation requested through the UI or API.

**[Result Validation] Response Consistency Check**
- Checks a completed response against the Core result before returning it.

#### Fallback

**[Input Handling] Alternate Request Reading**
- Reads the same request values from query parameters when the request body cannot be read.

**[Core Processing] Partial Preview Display**
- Displays the available preview items when some items cannot be loaded.

**[Result Validation] Alternate Response Certification**
- Uses an independent check when the primary completed-response check cannot run, without changing response values.

#### Shutdown

**[Input Handling] Invalid Request Rejection**
- Rejects a request when required parameters are missing.

**[Core Processing] Execution Request Failure**
- Ends the request when the Core operation cannot be started.

**[Result Validation] Invalid Response Rejection**
- Does not return a result when the response cannot be matched to the requested operation.
```
