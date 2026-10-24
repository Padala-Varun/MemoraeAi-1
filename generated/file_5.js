/**
 * Username Validation Module
 * Handles username availability checking
 */

let usernameCheckTimeout = null;
let lastCheckedUsername = '';

/**
 * Initializes username validation
 */
function initUsernameValidation() {
    const usernameInput = document.getElementById('signup-username');
    const availabilityEl = document.getElementById('username-availability');

    if (!usernameInput || !availabilityEl) return;

    usernameInput.addEventListener('input', () => {
        const username = usernameInput.value.trim();

        // Clear previous timeout
        if (usernameCheckTimeout) {
            clearTimeout(usernameCheckTimeout);
        }

        // Only check if username has changed and is valid
        if (username && username !== lastCheckedUsername && validateUsername(username)) {
            // Debounce the check to avoid excessive API calls
            usernameCheckTimeout = setTimeout(() => {
                checkUsernameAvailability(username, availabilityEl);
            }, 500);
        } else {
            availabilityEl.textContent = '';
            availabilityEl.className = 'input-feedback';
        }
    });
}

/**
 * Checks username availability
 * @param {string} username - Username to check
 * @param {HTMLElement} availabilityEl - Element to display availability status
 */
async function checkUsernameAvailability(username, availabilityEl) {
    if (!username || !availabilityEl) return;

    lastCheckedUsername = username;

    try {
        const isAvailable = await api.checkUsernameAvailability(username);

        if (isAvailable) {
            availabilityEl.textContent = 'Username is available!';
            availabilityEl.className = 'input-feedback valid';
        } else {
            availabilityEl.textContent = 'Username is already taken.';
            availabilityEl.className = 'input-feedback invalid';
        }
    } catch (error) {
        console.error('Error checking username availability:', error);
        availabilityEl.textContent = 'Could not check availability. Please try again.';
        availabilityEl.className = 'input-feedback invalid';
    }
}

// Export functions for other modules
window.initUsernameValidation = initUsernameValidation;