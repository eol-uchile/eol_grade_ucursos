# Eol Grade Ucursos

Question report in CSV

# Install

    docker-compose exec lms pip install -e /openedx/requirements/eol_grade_ucursos
    docker-compose exec lms_worker pip install -e /openedx/requirements/eol_grade_ucursos

## TESTS
**Prepare tests:**

    > cd .github/
    > docker-compose run lms /openedx/requirements/eol_grade_ucursos/.github/test.sh
