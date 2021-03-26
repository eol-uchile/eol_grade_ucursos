function export_grade(e){
    cleanGradeUcursos()
    e.disabled = true;
    document.getElementById('gradeucursos_curso').disabled = true;
    document.getElementById('gradeucursos_grade_type').disabled = true;
    var loading = document.getElementById('ui-loading-gradeucursos-load');
    loading.style.display = "block";
    var data = {
        'curso': document.getElementById('gradeucursos_curso').value,
        'grade_type': document.getElementById('gradeucursos_grade_type').value
    }
    GradeUcursosData(data)
}
function GradeUcursosData(report_data){
    var post_url = document.getElementById('gradeucursos_data_button').getAttribute('aria-controls')
    $.ajax({
        dataType: 'json',
        type: 'POST',
        url: post_url,
        data: report_data,
        success: function(data) {
            if (data["status"] == 'Generating' || data["status"] == 'AlreadyRunningError'){
                setTimeout(function(){ GradeUcursosData(report_data); }, 5000);
            }
            if (data["status"] == 'Generated'){
                return GradeUcursosDataSuccess();
            }
            if (data["status"] == 'Error'){
                return GradeUcursosDataError(data);
            }
        },
        error: function() {
            var aux_error = document.getElementById('report_error');
            aux_error.style.display = "block";
            var loading = document.getElementById('ui-loading-gradeucursos-load');
            loading.style.display = "none";
            document.getElementById('gradeucursos_curso').disabled = false;
            document.getElementById('gradeucursos_grade_type').disabled = false;
        }
    })
}
function GradeUcursosDataSuccess(){
    document.getElementById('gradeucursos_curso').disabled = false;
    document.getElementById('gradeucursos_grade_type').disabled = false;
    document.getElementById('gradeucursos_button').click();
    var loading = document.getElementById('ui-loading-gradeucursos-load');
    loading.style.display = "none";
    document.getElementById('gradeucursos_data_button').disabled = false;
}
function GradeUcursosDataError(data){
    if (data['empty_course']){
        var aux_error = document.getElementById('empty_course');
        aux_error.style.display = "block";
    }
    if (data['error_curso']){
        var aux_error = document.getElementById('error_curso');
        aux_error.style.display = "block";
    }
    if (data['user_permission']){
        var aux_error = document.getElementById('user_permission');
        aux_error.style.display = "block";
    }
    if (data['error_grade_type']){
        var aux_error = document.getElementById('error_grade_type');
        aux_error.style.display = "block";
    }
    if (data['report_error']){
        var aux_error = document.getElementById('report_error');
        aux_error.style.display = "block";
    }
    if (data['error_grade_cutoff']){
        var aux_error = document.getElementById('error_grade_cutoff');
        var aux_error_span = document.getElementById('error_grade_cutoff_span');
        aux_error_span.textContent = data['curso']
        aux_error.style.display = "block";
        
    }
    if (data['error_model']){
        var aux_error = document.getElementById('error_model');
        aux_error.style.display = "block";
    }
    var loading = document.getElementById('ui-loading-gradeucursos-load');
    loading.style.display = "none";
    document.getElementById('gradeucursos_data_button').disabled = false
    document.getElementById('gradeucursos_curso').disabled = false;
    document.getElementById('gradeucursos_grade_type').disabled = false;
}
function cleanGradeUcursos(){
    document.getElementById('ui-loading-gradeucursos-load').style.display = "none";
    document.getElementById('empty_course').style.display = "none";
    document.getElementById('error_curso').style.display = "none";
    document.getElementById('user_permission').style.display = "none";
    document.getElementById('error_grade_type').style.display = "none";
    document.getElementById('report_error').style.display = "none";
}