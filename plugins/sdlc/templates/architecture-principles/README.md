# Architecture principles

The knowledge base of the sdlc architecture judge. It judges the code of every plan phase against these files, not against what a model learned in training, so it is only as good as what is written here. Describe, update and improve them: when a review finds a problem the judge missed, add the principle that would have caught it.

One principle per file, `NN-short-name.md`, in this shape:

```markdown
# <Principle>

Rule: <one sentence the judge can check against a diff>
Why: <the failure it prevents>
Applies to: <paths or layers>
Good: <a pointer to code that follows it, `path:line`>
Bad: <what a violation looks like>
Exceptions: <when it does not apply, and who decides>
```

Start with the rules reviewers repeat most often in PR comments.
