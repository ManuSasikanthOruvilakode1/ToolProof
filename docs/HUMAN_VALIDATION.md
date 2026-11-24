# Checking the benchmark tasks by hand

Thank you for helping. ToolProof tests AI agents on customer-service requests for a made-up
online store. Before the test questions are frozen, a few people try 20 of them by hand. Doing
this tells us two things:

- whether each request is clear enough that a careful person knows what to do;
- whether the automatic checker marks a correct attempt as correct and a wrong one as wrong.

It takes about an hour. You don't need to know anything about AI, and you can't break anything:
every attempt runs on a private copy of the store's data.

## Your rater ID

You will be given an ID such as `rater_a`. Use only that ID. Please don't type your name, or
anyone else's, anywhere, including in the notes.

## Setup (once)

You need [uv](https://docs.astral.sh/uv/) and a copy of the repository.

```bash
git clone <repository-url> ToolProof
cd ToolProof
uv sync
```

## Doing the tasks

Run this to start your next task:

```bash
uv run toolproof bench try --rater rater_a
```

You'll see a request, as if a colleague had sent it to you. Work it out using the commands
below, exactly as an agent would:

| Command | What it does |
|---|---|
| `tools` | Lists the tools and their parameters |
| `call <tool> <json>` | Runs a tool, e.g. `call get_order {"order_id": 9031}` |
| `answer <text>` | Your final reply to the colleague; this ends the attempt |
| `quit` | Stops without saving anything |

Some tips:

- `search_docs` finds the store's policies. Check the policy before you refund anything.
- `sql_query` runs read-only SQL. The tool list shows the tables.
- `ask_user` asks the colleague a question. Use it if the request could mean more than one thing.
- A tool can fail now and then (a "timeout"). That's deliberate. Decide what a careful person
  would do.
- If a request should be refused, don't take the action. Explain why in your answer.

After you answer, the checker shows whether it passed your attempt. It then asks you two
questions:

1. **Do you agree with this verdict?** Answer "n" if you think your answer was right but it
   failed, or wrong but it passed.
2. **Was the request clear enough to know what to do?** Answer "n" if you had to guess what
   was wanted.

Use the notes to say what was confusing. Then run the command again for the next task. When
all 20 are done it tells you so.

## When everyone has finished

The project owner runs:

```bash
uv run toolproof bench agreement
```

This shows how often raters agreed with the checker, and lists every task someone disagreed
with or found unclear. Those tasks are fixed or removed before the test set is locked. Answers
are stored in `data/labels/human_validation.csv` under rater IDs only.
