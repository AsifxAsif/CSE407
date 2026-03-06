document.addEventListener("DOMContentLoaded", function () {
    let deviceDataChart = null; // Initialize chart as null
    let currentRoomId = null; // Declare currentRoomId in a scope accessible to all listeners

    // Define the room limit as a single, accessible constant
    const ROOM_LIMIT = 6;

    // Function to calculate total consumption and cost
    function calculateTotalConsumption(data) {
        if (!data || data.length === 0) {
            return { totalConsumption: 0, totalCost: 0, breakdown: [] };
        }

        let totalEnergyKWH = 0;
        let priceRanges = [
            { limit: 75, price: 5.26 },
            { limit: 200, price: 7.20 },
            { limit: 300, price: 7.59 },
            { limit: 400, price: 8.02 },
            { limit: 600, price: 12.67 },
            { limit: Infinity, price: 14.61 }
        ];

        // Using trapezoidal rule for more accurate consumption calculation
        for (let i = 1; i < data.length; i++) {
            const t1 = parseUTCDate(data[i - 1].timestamp);
            const t2 = parseUTCDate(data[i].timestamp);
            const deltaHours = (t2.getTime() - t1.getTime()) / (1000 * 3600);
            const avgWatt = (data[i].watt + data[i - 1].watt) / 2;
            totalEnergyKWH += (avgWatt * deltaHours) / 1000;
        }

        let totalConsumption = totalEnergyKWH;
        let totalCost = 0;
        let remainingUnits = totalConsumption;
        let breakdown = [];
        priceRanges.forEach((range, index) => {
            if (remainingUnits > 0) {
                let unitsInThisRange = (index === 0) ? Math.min(remainingUnits, range.limit) : Math.min(remainingUnits, range.limit - priceRanges[index - 1].limit);
                let costInThisRange = unitsInThisRange * range.price;
                totalCost += costInThisRange;
                breakdown.push(`${unitsInThisRange.toFixed(2)} * ${range.price.toFixed(2)}`);
                remainingUnits -= unitsInThisRange;
            }
        });
        return { totalConsumption, totalCost, breakdown };
    }

    // Function to parse UTC date and adjust for local time zone
    function parseUTCDate(utcDateStr) {
        const date = new Date(utcDateStr);
        const localDate = new Date(date.getTime() + date.getTimezoneOffset() * 60000); // Adjust for local timezone offset
        return localDate;
    }

    // Update the metrics on the card and modal
    function updateCardMetrics(room_id, data) {
        const { totalConsumption, totalCost, breakdown } = calculateTotalConsumption(data);

        // Update modal metrics
        const modalTotalUnitElement = document.getElementById("totalUnit");
        const modalTotalCostElement = document.getElementById("totalCost");
        const modalTotalCostStepsElement = document.getElementById("totalCostSteps");

        if (modalTotalUnitElement) modalTotalUnitElement.textContent = totalConsumption.toFixed(2);
        if (modalTotalCostElement) modalTotalCostElement.textContent = totalCost.toFixed(2);
        if (modalTotalCostStepsElement) modalTotalCostStepsElement.textContent = breakdown.join(' + ') + ` = ${totalCost.toFixed(2)}`;

        // Update main card metrics
        const totalUnitsElement = document.getElementById(`totalUnits-${room_id}`);
        const totalCostOnCardElement = document.getElementById(`totalCostOnCard-${room_id}`);
        if (totalUnitsElement) totalUnitsElement.textContent = totalConsumption.toFixed(2);
        if (totalCostOnCardElement) totalCostOnCardElement.textContent = totalCost.toFixed(2);
    }

    // Update the chart with room data
    function updateChart(room_id, data) {
        if (!data || data.length === 0) {
            console.error("No data available for room " + room_id);
            if (deviceDataChart) {
                deviceDataChart.destroy();
                deviceDataChart = null;
            }
            return;
        }
        const timestamps = data.map(item => parseUTCDate(item.timestamp));
        const currentValues = data.map(item => item.current);
        const voltageValues = data.map(item => item.voltage);
        const wattValues = data.map(item => item.watt);
        const ctx = document.getElementById('deviceDataChart').getContext('2d');
        if (!ctx) {
            console.error("Chart context not found!");
            return;
        }
        if (deviceDataChart) deviceDataChart.destroy();
        deviceDataChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: timestamps,
                datasets: [{
                    label: 'Current (A)',
                    data: currentValues,
                    borderColor: 'rgba(75, 192, 192, 1)',
                    backgroundColor: 'rgba(75, 192, 192, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    hitRadius: 5
                }, {
                    label: 'Voltage (V)',
                    data: voltageValues,
                    borderColor: 'rgba(153, 102, 255, 1)',
                    backgroundColor: 'rgba(153, 102, 255, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    hitRadius: 5
                }, {
                    label: 'Power (W)',
                    data: wattValues,
                    borderColor: 'rgba(255, 159, 64, 1)',
                    backgroundColor: 'rgba(255, 159, 64, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    hitRadius: 5
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'minute',
                            tooltipFormat: 'dd-MM-yyyy; hh:mm a',
                            displayFormats: {
                                minute: 'dd-MM-yyyy; hh:mm a',
                            },
                            timezone: 'Asia/Dhaka',
                        },
                        title: {
                            display: true,
                            text: 'Date & Time (BST)',
                        },
                        adapters: {
                            date: {
                                locale: typeof enUS !== 'undefined' ? enUS : null,
                            },
                        },
                    },
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Value',
                        },
                    },
                },
                plugins: {
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                    }
                }
            }
        });
    }

    // Load data for all rooms on page load
    function loadAllRoomData() {
        for (let roomId = 1; roomId <= ROOM_LIMIT; roomId++) {
            fetch(`/api/data/${roomId}`)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    const { totalConsumption, totalCost } = calculateTotalConsumption(data);
                    const totalUnitsElement = document.getElementById(`totalUnits-${roomId}`);
                    const totalCostOnCardElement = document.getElementById(`totalCostOnCard-${roomId}`);

                    if (totalUnitsElement) {
                        totalUnitsElement.textContent = totalConsumption.toFixed(2);
                    }
                    if (totalCostOnCardElement) {
                        totalCostOnCardElement.textContent = totalCost.toFixed(2);
                    }
                })
                .catch(error => {
                    console.error(`Error loading data for room ${roomId}:`, error);
                });
        }
    }

    // Dedicated function to fetch and render data for the modal
    function fetchAndRenderData(roomId) {
        if (!roomId) return;
        const fromDateTime = document.getElementById("fromDateTime").value;
        const toDateTime = document.getElementById("toDateTime").value;
        const url = `/api/data/${roomId}?from=${fromDateTime}&to=${toDateTime}`;
        fetch(url)
            .then(response => {
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                return response.json();
            })
            .then(data => {
                updateCardMetrics(roomId, data);
                updateChart(roomId, data);
            })
            .catch(error => console.error(`Error loading JSON data for room ${roomId}:`, error));
    }

    // Event listener for the room buttons
    document.querySelectorAll(".Btn-Container").forEach(button => {
        button.addEventListener("click", function () {
            const roomId = this.getAttribute("data-room-id");
            currentRoomId = roomId;
            const modal = document.getElementById("dataModal");
            modal.style.display = "block";
            fetchAndRenderData(roomId);
        });
    });

    // Event listeners for the date and time inputs to trigger a data refresh
    const fromDateTimeInput = document.getElementById("fromDateTime");
    const toDateTimeInput = document.getElementById("toDateTime");
    fromDateTimeInput.addEventListener("change", () => fetchAndRenderData(currentRoomId));
    toDateTimeInput.addEventListener("change", () => fetchAndRenderData(currentRoomId));

    // Toggle power function
    document.querySelectorAll('.toggle-switch').forEach(toggle => {
        toggle.addEventListener('change', async (e) => {
            const roomId = e.target.getAttribute('data-room-id');
            const url = e.target.checked ? `/on/${roomId}` : `/off/${roomId}`;
            try {
                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                await response.json();
                fetchStatus(roomId);
            } catch (error) {
                console.error('Failed to toggle power:', error);
                e.target.checked = !e.target.checked;
            }
        });
    });

    async function fetchStatus(roomId) {
        try {
            const res = await fetch(`/status/${roomId}`);
            const s = await res.json();
            const toggleSwitch = document.getElementById(`toggle-${roomId}`);
            if (toggleSwitch) {
                // Explicitly set the switch to the value returned by the API
                toggleSwitch.checked = s.switch;
            }
        } catch (err) {
            console.error(err);
        }
    }

    // Update the status for rooms 1 to 6
    function updateAllStatuses() {
        for (let roomId = 1; roomId <= ROOM_LIMIT; roomId++) {
            fetchStatus(roomId);
        }
    }

    // Download CSV functionality
    const downloadCsvButton = document.querySelector('.button_lg');
    downloadCsvButton.addEventListener('click', async function () {
        const roomId = currentRoomId;
        if (!roomId) {
            alert("Please open a room's data view before downloading.");
            return;
        }
        const fromDateTime = document.getElementById("fromDateTime").value;
        const toDateTime = document.getElementById("toDateTime").value;
        const url = `/api/download-csv/${roomId}?from=${fromDateTime}&to=${toDateTime}`;
        try {
            const response = await fetch(url);
            const contentType = response.headers.get("content-type");
            if (!response.ok) {
                const errorData = await response.json();
                alert(`Error: ${errorData.error}`);
                return;
            }
            if (contentType && contentType.includes("application/json")) {
                const data = await response.json();
                if (data.success) {
                    downloadFile(data.part1_data, `room_${roomId}_data_part1.csv`);
                    downloadFile(data.part2_data, `room_${roomId}_data_part2.csv`);
                } else {
                    console.error("Error downloading data:", data.error);
                }
            } else if (contentType && contentType.includes("text/csv")) {
                const blob = await response.blob();
                downloadFile(blob, `room_${roomId}_data.csv`);
            } else {
                console.error("Unknown response type:", contentType);
            }
        } catch (error) {
            console.error("Failed to download CSV:", error);
            alert("An error occurred while downloading the data. Please try again.");
        }
    });

    function downloadFile(content, fileName) {
        const blob = (content instanceof Blob) ? content : new Blob([content], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement("a");
        const url = URL.createObjectURL(blob);
        link.setAttribute("href", url);
        link.setAttribute("download", fileName);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    document.getElementById("closeModalBtn").addEventListener("click", function () {
        const modal = document.getElementById("dataModal");
        modal.style.display = "none";
        if (deviceDataChart) {
            deviceDataChart.destroy();
            deviceDataChart = null;
        }
        currentRoomId = null;
    });

    window.onclick = function (event) {
        const modal = document.getElementById("dataModal");
        if (event.target === modal) {
            modal.style.display = "none";
            if (deviceDataChart) {
                deviceDataChart.destroy();
                deviceDataChart = null;
            }
            currentRoomId = null;
        }
    };

    // User Manual Modal functionality
    document.getElementById("openManualButton").addEventListener("click", function () {
        const modal = document.getElementById("userManualModal");
        modal.style.display = "block";
    });

    document.getElementById("closeManualModalBtn").addEventListener("click", function () {
        const modal = document.getElementById("userManualModal");
        modal.style.display = "none";
    });

    window.onclick = function (event) {
        const modal = document.getElementById("userManualModal");
        if (event.target === modal) {
            modal.style.display = "none";
        }
    };

    // Initial data load and status checks
    loadAllRoomData();
    setInterval(updateAllStatuses, 5000);
});
