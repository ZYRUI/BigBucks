function stock_info()
{
    let symbol=document.getElementById("stock-history").value;
    const url = `/find_stock_info?stock_name=${symbol}`;

    fetch(url)
        .then(response => response.json())
        .then(data => {
            let table = '<table><thead><tr><th>Date</th><th>Close Price</th><th>SPY Index</th></tr></thead><tbody>';
            for (let i = 0; i < data.dates.length; i++) {
                table += `<tr><td>${data.dates[i]}</td><td>${data.close_prices[i]}</td><td>${data.spyPrices[i]}</td></tr>`;
            }

            table += '</tbody></table>';
            document.getElementById('stock-table').innerHTML = table;
            let trace1 = {
                x: data.dates,
                y: data.close_prices,
                mode: 'lines',
                name: `${symbol} Close Price`,
                line: {
                    color: 'rgba(75, 192, 192, 1)',
                },
            };
            let trace2 = {
                x: data.dates,
                y: data.spyPrices,
                mode: 'lines',
                name: 'SPY Index',
                line: {
                    color: 'rgba(255, 0, 0, 1)',
                },
            };

            let layout = {
                title: `${symbol} Last Five Year Stock Chart`,
                xaxis: {
                    title: 'Date',
                },
                yaxis: {
                    title: 'Close Price',
                },
            };

            Plotly.newPlot('stock-chart', [trace1,trace2], layout);
        });
}
