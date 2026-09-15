# H5P MCP Quiz Generator (Python)

Generate **valid H5P quiz packages (`.h5p`)** from **pure Python** via an **MCP server** (FastMCP). Designed to be used by **Claude Desktop**, **Cursor**, or any MCP-compatible agent—**no frontend** required.

This project outputs real H5P package structure:

- `h5p.json`
- `content/content.json`

It **does not bundle H5P libraries** (that’s normal for content exports). Your target platform (Moodle, Lumi, etc.) must have these content types installed:

- `H5P.MultiChoice`
- `H5P.TrueFalse`
- `H5P.Blanks`
- `H5P.QuestionSet`
- `H5P.InteractiveVideo`
- `H5P.InteractiveBook` (with `H5P.Column` and `H5P.AdvancedText`)

## Project structure

```
h5p_mcp/
├── server.py
├── requirements.txt
├── README.md
├── templates/
│   ├── mcq/
│   ├── truefalse/
│   ├── blanks/
│   ├── questionset/
│   ├── interactivevideo/
│   └── interactivebook/
├── libraries.py
├── generators/
│   ├── mcq_generator.py
│   ├── truefalse_generator.py
│   ├── blanks_generator.py
│   ├── questionset_generator.py
│   ├── interactivevideo_generator.py
│   └── interactivebook_generator.py
├── exporters/
│   └── h5p_exporter.py
├── validators/
│   └── quiz_validator.py
├── utils/
│   ├── zip_utils.py
│   └── file_utils.py
├── models/
│   └── quiz_models.py
└── exports/
```

## Setup

### Requirements
- Python **3.12+**

### Install

From the `h5p_mcp/` directory:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Run the MCP server

```bash
python -m h5p_mcp.server
```

By default this runs an MCP stdio server (ideal for Claude Desktop / Cursor integrations).

## Connect to Claude Desktop

In Claude Desktop, add an MCP server configuration pointing to your Python executable and `server.py`.

Example (conceptual):

```json
"H5P_MCP": {
      "command": "python",
      "args": ["-m", "h5p_mcp.server"],
      "env": {
        "PYTHONPATH": "C:\\Users\\msij\\Desktop\\MCP_H5p"
      }
    }
```

## Connect to Cursor

In Cursor, configure an MCP server and point it at the same `python server.py` entrypoint.

## MCP tools provided

- `create_mcq_quiz(title, question, choices, correct_answer, explanation)`
- `create_true_false_quiz(title, question, correct_answer, explanation)`
- `create_fill_blanks_quiz(title, text, answers)`
- `create_questionset_quiz(title, intro, questions, pass_percentage)`
- `create_interactive_video(title, video_url, interactions, summary, start_video_at)`
- `create_interactive_book(title, chapters, cover_description, show_cover, base_color, display_summary)`
- `export_h5p(quiz_data, output_name)`
- `validate_h5p(path)`
- Bonus:
  - `export_h5p_batch(quizzes, name_prefix)`
  - `markdown_to_quizzes(markdown)`
  - `h5p_prompt_helpers()`

## Example prompts for an AI agent

### Create and export an MCQ

Ask your agent to:

- Call `create_mcq_quiz` with:
  - title: “Basic Math”
  - question: “What is 2 + 2?”
  - choices: ["3","4","5"]
  - correct_answer: "4"
  - explanation: "2 + 2 equals 4."
- Then call `export_h5p` with:
  - quiz_data: (result from create tool)
  - output_name: "basic_math_mcq"

### Create and export a Fill in the Blanks

Use blanks text with **asterisk-wrapped answers** (H5P.Blanks convention):

- text: `"The capital of France is *Paris*."`

And provide answers list to validate:
- answers: ["Paris"]

## Generate sample `.h5p` files

Run:

```bash
python -m h5p_mcp.server --generate-samples
```

This writes a **set of sample `.h5p` files** (including a mixed-type `QuestionSet`) into `exports/`.

## Interactive Video

Put questions on a video timeline. The video is **referenced by URL and never
copied into the package** — embedding media would exceed typical LMS upload
limits, and H5P resolves the source at playback time. YouTube links and direct
`.mp4` / `.webm` / `.ogv` files are both detected automatically.

Call `create_interactive_video` with a list of interactions:

| Field | Required | Meaning |
|-------|----------|---------|
| `time` | yes | Seconds into the video where the question appears |
| `question` | yes | A canonical quiz dict (`mcq`, `truefalse` or `blanks`) |
| `duration` | no | Seconds it stays visible (default `10`) |
| `pause` | no | Pause the video when it appears (default `true`) |
| `display` | no | `"button"` to click open, or `"poster"` shown over the video |
| `label` | no | Caption next to the button |

Interactions are sorted by `time` during validation, so the order you pass them
in does not matter. Then call `export_h5p` as usual.

## Interactive Book

A multi-chapter book mixing prose with graded activities. Each chapter is one
page; each page holds an ordered list of sections.

Call `create_interactive_book` with a list of chapters:

| Field | Required | Meaning |
|-------|----------|---------|
| `title` | yes | Chapter name, shown in the table of contents |
| `sections` | yes | Ordered blocks on that page |

A section is either a prose block or a quiz dict:

```json
{"type": "text", "heading": "Overview", "body": "First para.\n\nSecond para."}
{"type": "truefalse", "title": "Check", "question": "...", "correct_answer": true}
```

`body` is **plain text, not HTML**. Blank lines separate paragraphs, single
newlines are soft wraps, and any markup typed in is escaped and appears
literally. Rich formatting beyond an optional `heading` is not supported yet.

## Fill in the Blanks

Wrap each answer in asterisks: `"The capital of France is *Paris*."` Pass the
same answers in the `answers` list and they are checked against the text.

Author text is escaped on the way out, so `<`, `&` and quotes are safe to use.
The asterisk delimiters are preserved, but an answer that *is* a markup
character is escaped too — a gap whose answer is `<` is stored as `*&lt;*`.
Use `instructions` to override the default task description.

## Markdown-to-quiz format (bonus)

```text
### MCQ: Basic Math
Q: What is 2 + 2?
- [ ] 3
- [x] 4
- [ ] 5
Explanation: 2 + 2 equals 4.

### TF: Astronomy
Q: The Earth orbits the Sun.
A: true
Explanation: It takes about one year.

### Blanks: Capitals
Text: The capital of France is *Paris*.
Answers: Paris
```

Then:
- Call `markdown_to_quizzes(markdown)` to get canonical quiz objects
- Call `export_h5p_batch(quizzes, name_prefix)` to export them

## Notes on Moodle / Lumi compatibility

- The produced `.h5p` contains content JSON compatible with the declared library.
- Moodle/Lumi must already include the relevant H5P libraries (content types).
- Validation in this repo checks package shape + JSON sanity and detects obvious issues early.

## License

Apache 2.

