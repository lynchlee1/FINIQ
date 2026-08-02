## Behavior Classification Rules
### 1. Purpose
- This document explains how to categorise and describe system behavior using consistent criteria.
- Carefully check the conditions and functions of system behavior to make sure that same behavior doesn't get classified differently across documents.
<br>

Every operation must be able to answer the following three questions:
1. Does it affect the resulting data, or is it the way the UI · API execute?
2. Does it operate under the right conditions, or does it operate after an unexpected failure?
3. What does it directly control: input, result generation, or result validation?

### 2. Rules
- Keep each rule focused on one one functionality.
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
- **Behaviour** distinguishes between normal conditions and how failures are handled.
  - First, determine whether it is a feature.
  - Only when it is not a feature, distinguish between fallback and shutdown.
- **Feature** is a set of rules for processing normal input and data.
  - It includes selecting or rejecting values.
  - It includes normal operations creating empty results.
- **Fallback** is a set of rules for using different values, methods, or reduces the scope of processing in order to continue in the event of an unexpected failure.
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
- **Responsibility** distinguishes which part of an operation a rule directly controls.
- **Input Handling** reads input and converts it into values that can be used for execution.
  - It includes checking the format and required values before execution begins.
- **Core Processing** uses the accepted input to produce the intended result.
  - It includes calculations, transformations, and checks required while producing the result.
- **Result Validation** checks the completed result and decides whether it can be saved or returned.
  - It includes checking the result's structure, completeness, and consistency.
- Do not classify every check as Result Validation.
  - A check on input is Input Handling.
  - A check on data used to produce the result is Core Processing.
  - A check on the completed result is Result Validation.

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

### 4. Writing Example
The following example shows every combination of Layer, Behavior, and Responsibility. An actual document should include only the rules that exist and mark an empty category as `None`.

```markdown
### Core

#### Feature

**[Input Handling] Date Range Validation**
- Accepts a start date that is earlier than or equal to the end date.

**[Core Processing] Record Filtering**
- Selects records that match the accepted date range.

**[Result Validation] Result Count Validation**
- Confirms that the reported count matches the number of selected records.

#### Fallback

**[Input Handling] Compatible Input Format**
- Uses a supported legacy input format when the current format cannot be read.

**[Core Processing] Failed Record Exclusion**
- Excludes a record that cannot be processed and continues with the remaining records.

**[Result Validation] Valid Result Preservation**
- Saves only the records that pass validation when some generated records are invalid.

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

**[Result Validation] Result Availability Check**
- Checks that the Core result is ready before returning it.

#### Fallback

**[Input Handling] Alternate Request Reading**
- Reads the same request values from query parameters when the request body cannot be read.

**[Core Processing] Partial Preview Display**
- Displays the available preview items when some items cannot be loaded.

**[Result Validation] Valid Response Item Display**
- Returns only the response items that pass validation when some items are invalid.

#### Shutdown

**[Input Handling] Invalid Request Rejection**
- Rejects a request when required parameters are missing.

**[Core Processing] Execution Request Failure**
- Ends the request when the Core operation cannot be started.

**[Result Validation] Invalid Response Rejection**
- Does not return a result when the response cannot be matched to the requested operation.
```
