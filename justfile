# Merge all open and passing dependabot pull requests
merge_dependabot:
    gh pr list --state=open --json=author,number \
    | jq '.[]' \
    | jq 'select(.author.login == "dependabot")' \
    | jq '.number' \
    | parallel "gh pr comment --body='@dependabot merge'"
