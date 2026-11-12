# Publish to a new GitHub repository

The connected GitHub integration used for this export can edit existing repositories but cannot create new repositories. Create an empty repository named `cdg-evidence-retrieval` in GitHub, **private initially** to review embedded licenses and source details, then publish this tree.

A straightforward local workflow from the unzipped archive:

```bash
cd cdg-research
# The ZIP is a source snapshot; initialize Git if needed.
git init
git add .
git commit -m "Initial CDG research archive"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/cdg-evidence-retrieval.git
git push -u origin main
```

Alternatively, after creating the empty repository, share its exact GitHub URL here so the connected GitHub tools can populate it. This archive contains no user authentication tokens and does not publish anything remotely by itself.
