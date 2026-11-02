# AI help on a step

Once a step has ended, its window offers help from an AI model: **Fix
failure** on a step that failed, **Analyze results** on one that finished.
The model reads what the step left and suggests. It never changes a setting
or starts a run: you decide what to do with its answer.

You use your own key, so your vendor bills you. With no key, the buttons stay
off.

## Add your key

On your **Account** page, under **AI key**, choose a vendor (Claude, OpenAI or
Gemini), paste your key, and press **Check and save**. AtomField asks the
vendor for its list of models, which proves the key works and fills the
**Model** menu.

AtomField keeps the key encrypted and only ever shows its last four
characters. **Remove** forgets it. Whoever runs the AtomField server holds the
secret that encrypts keys, so they could read yours: use a key you can cancel,
and ask your vendor for a spending limit.

## Ask

Double-click a step that has ended and press the button. The answer appears in
the **AI** tab, and stays there. Pressing the button again only opens it;
**Ask again** makes a new call, which your vendor bills again.

A step that was cancelled, or never ran because the step before it failed, has
nothing to ask about.

## What gets sent

One click sends one request to your vendor, with what the step left:

| | Fix failure | Analyze results |
|---|---|---|
| Error text, settings and what each means | all | all |
| Logs (the script's and the command's) | last 30,000 characters | last 6,000 |
| Input files (`.in`, `.inp`, `.win`) | 10,000 | 6,000 |
| Outputs the task declares (summary, tables) | 10,000 | 40,000 |
| Other text (`.out`, `.wout`) | last 10,000 | last 6,000 |
| Plots, with fewer points | no | 6,000 |
| The summary of each step before it | 4,000 | 4,000 |
| Listed docs pages, matching parts only | 15,000 | 10,000 |
| Names and sizes of files left on the cluster | yes | yes |

The scripts themselves are never sent, and neither is anything from an
unrelated job. Results still stay on your cluster, but a click does send these
small files to the vendor you chose.

The AI tab lists every file it read and how much of each. **See what was sent**
shows the exact text. It is kept with the run on the AtomField server, and goes
when the run is deleted.

## Does the vendor train on it?

A key stores nothing: it only says whose account to bill. What happens to the
data depends on the vendor and your plan, and vendors can change their terms,
so check theirs:

| Vendor and plan | Used for training? | Kept for |
|---|---|---|
| OpenAI | No, unless your organization opts in | Up to 30 days |
| Claude | No, without your permission | 30 days at most, 2 years if flagged |
| Gemini, paid | No | "A limited period", no number given |
| **Gemini, free** | **Yes, and people may read it** | Not stated |

Google says not to send sensitive, confidential or personal information to its
unpaid services. **Use a paid Gemini key for unpublished work.** AtomField can't
tell a free key from a paid one, so it warns whenever Gemini is chosen.

The terms: [OpenAI](https://developers.openai.com/api/docs/guides/your-data),
[Anthropic](https://privacy.claude.com/en/articles/7996868),
[Google](https://ai.google.dev/gemini-api/terms).

AtomField itself trains nothing.

## What it costs

A click reads about 20,000 tokens at most, and writes up to 16,000. Your vendor
sets the price: at most about 40 cents a click on `claude-opus-5-5`, usually
around 15, and about 1 cent on `claude-haiku-5-5`. The tab shows the tokens each
answer took. A limit per person per minute stops a stuck click from repeating.

## Read the answer with care

AI can be wrong, so check before you run again.

Each suggested setting is checked the way a real submission is. A setting the
step doesn't have, or a value it wouldn't accept, still shows, marked with what
is wrong with it, so you can see the model got it wrong. A suggestion that
passes is allowed, which doesn't make it right.

If you change a setting in **Parameters**, **Run** starts the whole pipeline
again, including the steps that worked.

## When it can't answer

- *The vendor refused this key*: check it, or add it again on the **Account**
  page.
- *Over a limit or out of credit*: that is your account with the vendor.
- *The model declined to read this*: its safety checks can wrongly refuse
  chemistry or biology text. Try another model. On the newest Claude models
  AtomField asks Anthropic to retry on another Claude model first, at that
  model's price, and the tab shows which model answered.
- *Left on the cluster, so not read*: files over 2 MB, apart from logs, stay on
  the cluster. If the answer needs one, read it yourself with **Get files**.
- *AI help is off on this server*: the server has no `AI_KEY_SECRET`. Ask
  whoever runs it.
