#!/bin/bash

if [ ! -d .venv ]; then
    virtualenv .venv
fi

if [ ! -f ".venv/flake8-diff.py" ]; then
    wget -q -P .venv https://raw.githubusercontent.com/NeCTAR-RC/flake8-diff/master/flake8-diff.py
fi

source .venv/bin/activate

diff requirements.txt .venv/requirements.txt >/dev/null 2>&1
REQUIREMENTS_CHANGED=$?
diff test-requirements.txt .venv/test-requirements.txt >/dev/null 2>&1
TEST_REQUIREMENTS_CHANGED=$?

if [ "$REQUIREMENTS_CHANGED" -ne 0 -o "$TEST_REQUIREMENTS_CHANGED" -ne 0 ]; then
    echo "Reinstalling"
    pip install -r requirements.txt -r test-requirements.txt
    cp requirements.txt test-requirements.txt .venv
fi


echo "Tests"
echo "====="
nosetests
NOSE_RESULT=$?
echo -e "\nPEP8"
echo "===="
python .venv/flake8-diff.py
FLAKE8_RESULT=$?
if [ $FLAKE8_RESULT -eq 0 ]; then
    echo "OK"
fi
echo

exit $FLAKE8_RESULT || $NOSE_RESULT
