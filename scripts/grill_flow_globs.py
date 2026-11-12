import fnmatch
DEFAULT_TEST_EXCLUDE = ["**/test/**","**/tests/**","**/*_test.*","**/*_spec.*","**/spec/**","**/__tests__/**","**/*.test.*","**/*.spec.*"]
DEFAULT_SKIP = ["**/package-lock.json","**/yarn.lock","**/*.min.js","**/dist/**","**/build/**"]
def _match(path, patterns):
    path = path.replace("\\", "/")
    return any(
        fnmatch.fnmatch(path, pat)
        or fnmatch.fnmatch("/" + path.lstrip("/"), pat)
        or fnmatch.fnmatch(path.split("/")[-1], pat)
        for pat in patterns
    )
def is_test_excluded(path, patterns=None):
    return _match(path, patterns or DEFAULT_TEST_EXCLUDE)
def is_skipped(path, patterns=None):
    return _match(path, patterns or DEFAULT_SKIP)
