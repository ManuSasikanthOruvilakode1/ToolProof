# Checking the benchmark tasks by hand

Thank you for helping. ToolProof tests AI agents on customer-service requests for a made-up
online store. Before the test questions are frozen, a few people try 20 of them by hand. Doing
this tells us two things:

- whether each request is clear enough that a careful person knows what to do;
- whether the automatic checker marks a correct attempt as correct and a wrong one as wrong.

It takes about an hour, and you can stop and carry on later. You don't need to know anything
about AI, and you can't break anything: every attempt runs on a private copy of the store's
data, and your attempts stay on your computer until you send the results file.

## Your rater ID

The project owner gives you an ID such as `rater_b`. Use only that ID. Please don't type your
name, or anyone else's, anywhere, including in the notes.

## Keeping it fair

- Work only through the commands below. Please don't open the project's files or folders:
  some of them contain the expected answers.
- Don't talk about the tasks with the other rater until you've both finished. The point is to
  see whether two people, working separately, judge them the same way.

## Setup (once, about five minutes)

1. Install **uv**, which sets up everything else, including Python.
   - Windows: open PowerShell and run
     `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
   - macOS or Linux: open a terminal and run
     `curl -LsSf https://astral.sh/uv/install.sh | sh`

   Then close the window and open a new one.

2. Get a copy of the project. With git:

   ```bash
   git clone https://github.com/ManuSasikanthOruvilakode1/ToolProof.git
   cd ToolProof
   ```

   Without git: open https://github.com/ManuSasikanthOruvilakode1/ToolProof, click **Code**,
   then **Download ZIP**. Unzip it, and in your terminal `cd` into the unzipped folder.

3. Run `uv sync`. The first time, this downloads Python and the project's libraries.

## Doing the tasks

Run this to start your next task, using your own ID:

```bash
uv run toolproof bench try --rater rater_b
```

You'll see a request, as if a colleague had sent it to you. Work it out using the commands
below, exactly as an agent would:

| Command | What it does |
|---|---|
| `tools` | Lists the tools, their parameters and the database tables |
| `call <tool> <json>` | Runs a tool, e.g. `call get_order {"order_id": 9031}` |
| `answer <text>` | Your final reply to the colleague; this ends the attempt |
| `quit` | Stops without saving this task |

Some tips:

- `search_docs` finds the store's policies, e.g. `call search_docs {"query": "late delivery"}`.
  Check the policy before you refund anything.
- `sql_query` runs read-only SQL, e.g. `call sql_query {"query": "SELECT * FROM customers WHERE
  last_name = 'Smith'"}`. Type `tools` to see the tables.
- `ask_user` asks the colleague a question. Use it if the request could mean more than one thing.
- A tool can fail now and then (a "timeout"). That's deliberate. Decide what a careful person
  would do.
- If a request should be refused, don't take the action. Explain why in your answer.
- Your answer is one line of text. Write it as you would reply to the colleague.

After you answer, the checker shows whether it passed your attempt. It then asks you two
questions:

1. **Do you agree with this verdict?** Answer "n" if you think your answer was right but it
   failed, or wrong but it passed.
2. **Was the request clear enough to know what to do?** Answer "n" if you had to guess what
   was wanted.

Use the notes to say what was confusing. Then run the command again for the next task. Each
finished task is saved straight away, so you can stop between tasks and carry on another day.
When all 20 are done it tells you so.

## Sending your answers back

When you've finished all 20, send the project owner this one file from your copy of the
project:

```
data/labels/human_validation.csv
```

It holds only your rater ID, the task IDs, the checker's verdicts, your two answers and your
notes. Please check that the notes contain no names before you send it.

## When everyone has finished

The project owner adds each rater's file to theirs and runs:

```bash
uv run toolproof bench agreement
```

This shows how often raters agreed with the checker, and lists every task someone disagreed
with or found unclear. Those tasks are fixed or removed before the test set is locked.
