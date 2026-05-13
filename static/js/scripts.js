// Scripts mejorados con DataTables y Bootstrap

document.addEventListener('DOMContentLoaded', function() {
    // Inicializar DataTables si existe la tabla
    const dataTable = document.getElementById('dataTable');
    if (dataTable) {
        $('#dataTable').DataTable({
            language: {
                url: '//cdn.datatables.net/plug-ins/1.13.8/i18n/es-ES.json'
            },
            responsive: true,
            paging: true,
            pageLength: 10,
            lengthMenu: [[10, 25, 50, 100, 500], [10, 25, 50, 100, 500]],
            searching: true,
            ordering: true,
            info: true,
            dom: '<"row g-3"<"col-md-6"l><"col-md-6"f>>rtip',
            drawCallback: function(settings) {
                // Animaciones suaves para las filas de la tabla
                const tbody = document.querySelector('#dataTable tbody');
                if (tbody) {
                    Array.from(tbody.rows).forEach(row => {
                        row.style.opacity = 0;
                        setTimeout(() => {
                            row.style.transition = 'opacity 0.3s';
                            row.style.opacity = 1;
                        }, 10);
                    });
                }
            }
        });
    }
    
    // Auto-enfocar el campo de ruta cuando se carga la página
    const rutaInput = document.getElementById('ruta_archivo');
    if (rutaInput && !rutaInput.value) {
        rutaInput.focus();
    }
    
    // Validación simple del formulario (sin alert)
    const form = document.querySelector('form');
    if (form) {
        form.addEventListener('submit', function(e) {
            const ruta = document.getElementById('ruta_archivo').value.trim();
            if (!ruta) {
                e.preventDefault();
                return false;
            }
        });
    }
    
    // Scroll suave a los resultados
    const resultsSection = document.querySelector('.results-section');
    if (resultsSection) {
        setTimeout(() => {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 300);
    }
    
    // Agregar tooltips si están disponibles
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
    
    // Mejorar la experiencia con tecla Enter en inputs
    document.querySelectorAll('.form-control').forEach(input => {
        input.addEventListener('keypress', function(e) {
            if (e.key === 'Enter' && input.id === 'ruta_archivo') {
                form.submit();
            }
        });
    });
});

// Función para exportar datos (opcional)
function exportTableToCSV() {
    const table = document.getElementById('dataTable');
    if (!table) return;
    
    let csv = [];
    const rows = table.querySelectorAll('tr');
    
    rows.forEach(row => {
        const cells = row.querySelectorAll('td, th');
        const cellData = Array.from(cells).map(cell => {
            return '"' + cell.textContent.trim().replace(/"/g, '""') + '"';
        });
        csv.push(cellData.join(','));
    });
    
    const csvContent = csv.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    
    link.setAttribute('href', url);
    link.setAttribute('download', 'datos_' + new Date().toISOString().slice(0, 10) + '.csv');
    link.style.visibility = 'hidden';
    
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
