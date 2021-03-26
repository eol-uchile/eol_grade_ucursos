# Eol Grade Ucursos

![https://github.com/eol-uchile/eol_grade_ucursos/actions](https://github.com/eol-uchile/eol_grade_ucursos/workflows/Python%20application/badge.svg)

Export the students' grades to an excel file (.xlsx)

# Install App

    docker-compose exec lms pip install -e /openedx/requirements/eol_grade_ucursos
    docker-compose exec lms_worker pip install -e /openedx/requirements/eol_grade_ucursos

# Install Theme

To enable export grade button in your theme add next file and/or lines code:

- _../themes/your_theme/lms/templates/instructor/instructor_dashboard_2/data_download.html_

    **add the script and css**

        <link rel="stylesheet" type="text/css" href="${static.url('gradeucursos/css/gradeucursos.css')}"/>
        <script type="text/javascript" src="${static.url('gradeucursos/js/gradeucursos.js')}"></script>

    **and add html button**

          %if 'has_gradeucursos' in section_data and section_data['has_gradeucursos']:
            <div class='gradeucursos-export'>
                <hr>
                <h4 class="hd hd-4">Exportar Notas</h4>
                <p>Seleccione la escala de nota ha exportar, presione el boton Exportar Notas y se generara un archivo Excel</p>
                <p>
                    <label for="gradeucursos_grade_type" style="clear: both; font-style: normal; font-family: 'Open Sans', 'Helvetica Neue', Helvetica, Arial, sans-serif">Escala de Nota:</label>
                    <select class="gradeucursos_select" name='gradeucursos_grade_type' id='gradeucursos_grade_type'>
                        <option value="seven_scale">1.0 - 7.0</option>
                        <option value="hundred_scale">0 - 100</option>
                        <option value="percent_scale">0.00 - 1.00</option>
                    </select>
                </p>
                <input hidden disabled type="text" name='curso' id="gradeucursos_curso" value="${section_data['gradeucursos_course']}"></input>
                <p><input id='gradeucursos_data_button' onclick="generate_data_gradeucursos(this)" type="button" name="gradeucursos-data" value="Exportar Notas" data-endpoint="${ section_data['gradeucursos_url_data'] }"/>
                <div class="gradeucursos-success-msg" id="gradeucursos-success-msg"></div>
                <div class="gradeucursos-warning-msg" id="gradeucursos-warning-msg"></div>
                <div class="gradeucursos-error-msg" id="gradeucursos-error-msg"></div>
                <hr>
            </div>
        %endif

- In your edx-platform add the following code in the function '_section_data_download' in _edx-platform/lms/djangoapps/instructor/views/instructor_dashboard.py_

        <try:
            from gradeucursos import views
            section_data['has_gradeucursos'] = True
            section_data['gradeucursos_url_data'] = reverse('gradeucursos-export:data')
            section_data['gradeucursos_course'] = six.text_type(course_key)
        except ImportError:
            section_data['has_gradeucursos'] = False
        
## TESTS
**Prepare tests:**

    > cd .github/
    > docker-compose run lms /openedx/requirements/eol_grade_ucursos/.github/test.sh