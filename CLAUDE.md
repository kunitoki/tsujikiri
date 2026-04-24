- never git add or commit
- always use python and tools via "uv run"
- use "just test" to test
- use "just test clang22 -k test_method_name" to test an individual test method
- use "just coverage" to coverage
- the product is used from CLI not as library
- in python files and tests, imports are only allowed at the top
- always use python type annotations
- feature is not finished until:
    * the feature is extensively tested, edge cases too not just happy paths
    * coverage is 100%
    * stubs are regenerated with "just stubs"
    * formatting is done with "just format"
    * type checks are performed with "just check"
    * documentation in docs/ is also reviewed and updated
