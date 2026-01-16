function generate_data_gradeucursos(input){
    cleanGradeUcursos()
    var success_div = document.getElementById('gradeucursos-success-msg');
    var error_div = document.getElementById('gradeucursos-error-msg');
    var supportEmail = error_div.dataset.supportEmail;
    var warning_div = document.getElementById('gradeucursos-warning-msg');
    var report_data = {
        'curso': input.getAttribute('data-course-id'),
        'grade_type': document.getElementById('gradeucursos_grade_type').value,
        'instructor_tab': true
    }
    var post_url = document.getElementById('gradeucursos_data_button').dataset.endpoint;
    $.ajax({
        dataType: 'json',
        type: 'POST',
        url: post_url,
        data: report_data,
        success: function(data) {
            if (data["status"] == 'Generating'){
              success_div.textContent = "El reporte de notas se esta generando, en un momento estará disponible para descargar.";
              success_div.style.display = "block";
            }
            if (data["status"] == 'AlreadyRunningError'){
              warning_div.textContent = 'El reporte ya se esta generando, por favor espere.'
              warning_div.style.display = "block";
            }
            if (data["status"] == 'Error'){
                return GradeUcursosDataError(data);
            }
        },
        error: function() {
            var errorMessage = 'Error al exportar las notas, actualice la página e intentelo nuevamente, si el error persiste contáctese con la mesa de ayuda {supportEmail}.';  
            error_div.textContent = errorMessage;
            error_div.style.display = "block";
        }
    })
}
function cleanGradeUcursos(){
    document.getElementById('gradeucursos-success-msg').style.display = "none";
    document.getElementById('gradeucursos-success-msg').textContent = "";
    document.getElementById('gradeucursos-error-msg').style.display = "none";
    document.getElementById('gradeucursos-error-msg').textContent = "";
    document.getElementById('gradeucursos-warning-msg').style.display = "none";
    document.getElementById('gradeucursos-warning-msg').textContent = "";
}
function GradeUcursosDataError(data){
    var error_msg = document.getElementById('gradeucursos-error-msg');
    if (data['user_permission']){
      error_msg.textContent = 'Usuario no tiene permisos para realizar esta acción.';
    }
    else {
      if (data['error_grade_cutoff']){
        error_msg.textContent = 'Este curso no tiene configurado el porcentaje de aprobación.'
      }
      else{
        var errorMessage = 'Error al exportar las notas, actualice la página e intentelo nuevamente, si el error persiste contáctese con la mesa de ayuda {supportEmail}.';
        error_msg.textContent = errorMessage;
      }
    }
    error_msg.style.display = "block";
}
