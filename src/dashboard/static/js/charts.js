// Chart color constants and utilities for Team Metrics Dashboard

// Semantic color system for consistent chart styling
const CHART_COLORS = {
    // Semantic colors for created/resolved patterns
    CREATED: '#e74c3c',      // Red - items added/created
    RESOLVED: '#2ecc71',     // Green - items completed/closed
    NET: '#3498db',          // Blue - difference/net change

    // Team identity colors
    TEAM_PRIMARY: '#3498db',     // Blue
    TEAM_SECONDARY: '#9b59b6',   // Purple

    // Activity type colors
    PRS: '#3498db',          // Blue
    REVIEWS: '#9b59b6',      // Purple
    COMMITS: '#27ae60',      // Green
    JIRA_COMPLETED: '#f39c12',  // Orange
    JIRA_WIP: '#e74c3c',     // Red

    // Status colors
    SUCCESS: '#27ae60',      // Green
    WARNING: '#f39c12',      // Orange
    DANGER: '#e74c3c',       // Red
    INFO: '#3498db',         // Blue

    // Pie chart palette (diverse colors)
    PIE_PALETTE: ['#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6', '#1abc9c', '#e67e22']
};

/**
 * Get theme-aware background and grid colors for Plotly charts
 * @returns {Object} Colors object for chart styling
 */
function getChartColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
        paper_bgcolor: isDark ? '#2d2d2d' : '#ffffff',
        plot_bgcolor: isDark ? '#2d2d2d' : '#ffffff',
        font_color: isDark ? '#e0e0e0' : '#2c3e50',
        grid_color: isDark ? '#444' : '#ecf0f1'
    };
}

/**
 * Get standard layout configuration for Plotly charts
 * @param {Object} customConfig - Custom configuration to merge
 * @returns {Object} Complete layout configuration
 */
function getChartLayout(customConfig = {}) {
    const colors = getChartColors();
    const defaultConfig = {
        paper_bgcolor: colors.paper_bgcolor,
        plot_bgcolor: colors.plot_bgcolor,
        font: { color: colors.font_color },
        xaxis: {
            gridcolor: colors.grid_color,
            color: colors.font_color
        },
        yaxis: {
            gridcolor: colors.grid_color,
            color: colors.font_color
        }
    };

    // Deep merge custom config with defaults
    return Object.assign({}, defaultConfig, customConfig);
}

/**
 * Apply semantic colors to trend chart data
 * @param {Array} weeks - Array of week labels
 * @param {Object} createdData - Created items by week
 * @param {Object} resolvedData - Resolved items by week
 * @returns {Array} Array of Plotly trace objects
 */
function getTrendChartTraces(weeks, createdData, resolvedData) {
    const netDifference = weeks.map(w => (createdData[w] || 0) - (resolvedData[w] || 0));

    return [
        {
            x: weeks,
            y: weeks.map(w => createdData[w] || 0),
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Created',
            line: { color: CHART_COLORS.CREATED, width: 2 },
            marker: { color: CHART_COLORS.CREATED, size: 6 },
            xaxis: 'x',
            yaxis: 'y'
        },
        {
            x: weeks,
            y: weeks.map(w => resolvedData[w] || 0),
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Resolved',
            line: { color: CHART_COLORS.RESOLVED, width: 2 },
            marker: { color: CHART_COLORS.RESOLVED, size: 6 },
            xaxis: 'x',
            yaxis: 'y'
        },
        {
            x: weeks,
            y: netDifference,
            type: 'scatter',
            mode: 'lines+markers',
            name: 'Net (Created - Resolved)',
            line: { color: CHART_COLORS.NET, width: 2 },
            marker: { color: CHART_COLORS.NET, size: 6 },
            xaxis: 'x2',
            yaxis: 'y2'
        }
    ];
}

// Export for use in templates
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { CHART_COLORS, getChartColors, getChartLayout, getTrendChartTraces };
}
