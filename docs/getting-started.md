# Getting started

AtomField turns calculation scripts into pipelines you build and run from
your browser, while the jobs run on your own cluster.

## 1. Sign in

Choose **Sign in** and use your Google account. Your lab's admin has to add
your address first. If you are refused, the page names the address Google
gave: that is the one to send them.

## 2. Connect your cluster

You do this once. A small program called the agent runs on the cluster's
login node and asks AtomField for work. Nothing connects into your cluster,
and AtomField never sees your cluster password. To set it up, follow
`docs/cluster-agent.md`. Until you have a cluster, **Run** stays off.

## 3. Start a pipeline

On **Sessions**, choose **New pipeline**. Pick a template, or drag tasks from
the list on the left onto the canvas, where each becomes a step. Link one
step to the next by dragging from the edge of one box to the next. Drop your
input files on the canvas.

## 4. Set each step

Double-click a step. Its **Parameters** tab shows what you can set, and the
small **i** beside each says what it means. Whatever you leave alone uses the
script's default, and **Reset** puts them all back.

## 5. Run it

Under **Run on**, check that your cluster is chosen. A ● beside it means its
agent is online; with a ○, jobs wait until it comes back. Press **Run**. The
top bar shows how far the run has got, and **Stop** ends it.

## 6. Read the results

Double-click a step again:

- **Logs** shows what the program printed.
- **Plots**, on steps that draw them, shows charts you can hover over and zoom.
- **Artifacts** shows the step's text files.

## 7. Get your files

Results stay on your cluster. **Get files** shows their folder and a command
to copy it to your own computer. For runs up to 1 GB you can also choose
**Make a download link**.
