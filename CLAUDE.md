Development Workflow
--------------------

You should execute the following CI steps after each code change or refactor to make code remains logically correct:

1. Create a virtual environment and install following dependencies:

   - `pytest`

2. Run the following unit tests:

   ```bash
   python -m pytest tests/ -v
   ```
