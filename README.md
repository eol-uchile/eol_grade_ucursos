# Eol Grade Ucursos

![Coverage Status](/coverage-badge.svg)

![https://github.com/eol-uchile/eol_grade_ucursos/actions](https://github.com/eol-uchile/eol_grade_ucursos/workflows/Python%20application/badge.svg)

Export the students' grades to an excel file (.xlsx)

# Install App

    docker compose exec lms pip install -e /openedx/requirements/eol_grade_ucursos
    docker compose exec lms_worker pip install -e /openedx/requirements/eol_grade_ucursos

# Install Theme

To enable the export eol grade ucursos interface, add the following code to your theme. This includes a conditional check to ensure the template only renders if the app is installed.

- _../themes/your_theme/lms/templates/instructor/instructor_dashboard_2/data_download.html_

    **add the mako template in the theme**

        <%
        gradeucursos_url = None
        gradeucursos_traceback = None
        try:
          gradeucursos_url = reverse('gradeucursos-export:data')
        except Exception as e:
          if settings.DEBUG:
            gradeucursos_traceback = traceback.format_exc()
        %>
        %if gradeucursos_traceback:
          <div class="gradeucursos_traceback" hidden>
            <pre>${gradeucursos_traceback}</pre>
          </div>
        %elif gradeucursos_url:
          <%include file="eol_grade_ucursos.html"/>
        %endif

### Adding new translations:

To extract and update any new translatable text, run the update command below. After manually filling in the new translations, run the compile command to update the .mo translation files.

### Commands

**Update**

    docker run -it --rm -w /code -v $(pwd):/code python:3.8 bash
    pip install -r requirements-i18n.in
    make update_translations

**Compile**

    docker run -it --rm -w /code -v $(pwd):/code python:3.8 bash
    pip install -r requirements-i18n.in
    make compile_translations

## TESTS
**Prepare tests:**

- Install **act** following the instructions in [https://nektosact.com/installation/index.html](https://nektosact.com/installation/index.html)

**Run tests:**
- In a terminal at the root of the project
    ```
    act -W .github/workflows/pythonapp.yml
    ```
