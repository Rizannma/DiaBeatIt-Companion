
const form = document.getElementById('profileForm');
const initialState = new FormData(form);
let initialValues = {};

for (let [key, value] of initialState.entries()) {
     initialValues[key] = value;
    }

     // Required fields for validation
    const requiredFields = ['gender', 'family_history_diabetes', 'cardiovascular_history', 'hypertension_history', 'height_cm', 'weight_kg'];

     // Set field error message
    function setFieldError(fieldId, message) {
        const field = document.getElementById(fieldId);
        const errorSpan = document.getElementById(`error-${fieldId}`);
                            
         if (message) {
             field.classList.add('invalid-field');
             if (errorSpan) errorSpan.textContent = message;
        } else {
             field.classList.remove('invalid-field');
            if (errorSpan) errorSpan.textContent = '';
     }
}

    // Validate single field
    function validateField(fieldId) {
        const field = document.getElementById(fieldId);
         if (!field) return true;

        // Check if field is empty
        if (!field.value || field.value === '') {
            setFieldError(fieldId, 'This field is required.');
            return false;
     }

        // Validate height and weight (now allowing decimals)
        if (fieldId === 'height_cm' || fieldId === 'weight_kg') {
        if (isNaN(parseFloat(field.value))) {
            setFieldError(fieldId, 'Must be a valid number');
            return false;
            }
        }

            setFieldError(fieldId, '');
            return true;
            }

            // Validate all required fields
            function validateAllFields() {
            let isValid = true;
            requiredFields.forEach(fieldId => {
            if (!validateField(fieldId)) {
                isValid = false;
            }
         });
            return isValid;
}

        // Add real-time validation on input/change
        requiredFields.forEach(fieldId => {
        const field = document.getElementById(fieldId);
        if (field) {
            field.addEventListener('input', () => validateField(fieldId));
            field.addEventListener('change', () => validateField(fieldId));
        }
});

    form.addEventListener('submit', async function(e) {
    e.preventDefault();

    // Validate all fields
    if (!validateAllFields()) {
    return;
    }

    const currentData = new FormData(form);
    let hasChanges = false;
    for (let [key, value] of currentData.entries()) {
        if (initialValues[key] !== value) {
            hasChanges = true;
        break;
    }
}

    if (!hasChanges) {
        showAlert('No changes detected', 'info');
    return;
    }

    try {
    const formData = new FormData(form);
    // Dynamically get the action URL from the form attribute to support static JS files
    const response = await fetch(form.action || window.location.href, {
    method: 'POST',
    body: formData,
    headers: {
    'X-Requested-With': 'XMLHttpRequest'
    }
});

    if (response.ok) {
    const html = await response.text();
    const parser = new DOMParser();
    const newDoc = parser.parseFromString(html, 'text/html');
    const newBMI = newDoc.querySelector('#bmi');
    
    if (newBMI) {
    document.querySelector('#bmi').value = newBMI.value;
    }
        showAlert('Profile saved successfully!', 'success');
        initialValues = {};
    
        for (let [key, value] of formData.entries()) {
        initialValues[key] = value;
    }
} else {
        showAlert('Failed to save profile. Please try again.', 'danger');
}
    } catch (error) {
        console.error('Error:', error);
        showAlert('An error occurred while saving. Please try again.', 'danger');
}
});

    function showAlert(message, type) {
    const container = document.getElementById('alertContainer');
    const alertDiv = document.createElement('div');
    
    // Added 'alert-dismissible' class (required for Bootstrap close buttons)
    alertDiv.className = `alert alert-${type === 'success' ? 'success' : type === 'danger' ? 'danger' : 'info'} alert-dismissible alert-custom`;
    alertDiv.role = 'alert';
    
    // Message first, then the Close button
    alertDiv.innerHTML = `
        <div class="d-flex align-items-center justify-content-between">
            <span>${message}</span>
            <button type="button" class="btn-close static-position" data-bs-dismiss="alert" aria-label="Close" style="position: relative; margin-left: 15px;"></button>
        </div>
    `;
    
    container.appendChild(alertDiv);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if(alertDiv.parentNode) {
            alertDiv.classList.add('alert-fade-out');
            setTimeout(() => alertDiv.remove(), 5000);
        }
    }, 5000);
}
