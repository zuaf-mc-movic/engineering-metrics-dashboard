// Theme Toggle Functionality
// Load saved theme preference or default to light mode
const currentTheme = localStorage.getItem('theme') || 'light';
document.documentElement.setAttribute('data-theme', currentTheme);

// Update button text based on current theme
function updateButtonText() {
    const theme = document.documentElement.getAttribute('data-theme');

    // Update standalone theme toggle button (if exists)
    const button = document.querySelector('.theme-toggle');
    if (button) {
        button.textContent = theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode';
    }

    // Update theme toggle in hamburger menu
    const menuButton = document.querySelector('.theme-toggle-menu');
    if (menuButton) {
        const icon = menuButton.querySelector('.theme-icon');
        const text = menuButton.querySelector('.theme-text');
        if (icon && text) {
            icon.textContent = theme === 'dark' ? '☀️' : '🌙';
            text.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
        }
    }
}

// Toggle theme function
function toggleTheme() {
    const theme = document.documentElement.getAttribute('data-theme');
    const newTheme = theme === 'dark' ? 'light' : 'dark';

    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);

    // Update button text
    updateButtonText();

    // Update Plotly charts if they exist
    updatePlotlyTheme(newTheme);
}

// Update Plotly chart themes
function updatePlotlyTheme(theme) {
    const isDark = theme === 'dark';

    const layout = {
        paper_bgcolor: isDark ? '#2d2d2d' : '#ffffff',
        plot_bgcolor: isDark ? '#2d2d2d' : '#ffffff',
        font: {
            color: isDark ? '#e0e0e0' : '#2c3e50'
        },
        xaxis: {
            gridcolor: isDark ? '#444' : '#ecf0f1',
            color: isDark ? '#e0e0e0' : '#2c3e50'
        },
        yaxis: {
            gridcolor: isDark ? '#444' : '#ecf0f1',
            color: isDark ? '#e0e0e0' : '#2c3e50'
        }
    };

    // Update all Plotly charts on the page
    const plotlyDivs = document.querySelectorAll('[id$="-comparison"], [id^="throughput-"]');
    plotlyDivs.forEach(div => {
        if (div.data) {  // Check if it's a Plotly chart
            Plotly.relayout(div.id, layout);
        }
    });
}

// Initialize button text on page load
document.addEventListener('DOMContentLoaded', function() {
    updateButtonText();
});
