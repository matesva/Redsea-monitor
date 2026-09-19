async function loadMonitorData() {
    try {
        const response = await fetch('./data.json?t=' + new Date().getTime());
        const data = await response.json();

        // 1. Převod data a času
        if (data.last_updated) {
            const updatedDate = new Date(data.last_updated);
            const now = new Date();
            const diffMs = now - updatedDate;
            const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
            const diffDays = Math.floor(diffHours / 24);

            let timeText = "";
            if (isNaN(updatedDate.getTime())) {
                timeText = data.last_updated;
            } else if (diffDays > 0) {
                timeText = `před ${diffDays} dny`;
            } else if (diffHours > 0) {
                timeText = `před ${diffHours} hodinami`;
            } else {
                timeText = "před chvílí";
            }
            document.getElementById('last-updated').innerText = `Aktualizováno ${timeText}`;
        }

        // 2. Ceny ropy a kurz
        if (data.oil_prices && data.oil_prices.brent) {
            document.getElementById('brent-price').innerText = `$${data.oil_prices.brent.value.toFixed(2)}`;
            document.getElementById('brent-date').innerText = data.oil_prices.brent.date;
        }
        if (data.usd_czk) {
            document.getElementById('usd-czk-price').innerText = `${data.usd_czk.value} CZK`;
        }

        // 3. Bezpečnostní úroveň a sentiment
        if (data.assessment) {
            const badge = document.getElementById('threat-badge');
            const level = data.assessment.threat_level || 'NEZNÁMÁ';
            badge.innerText = level;
            
            badge.className = 'badge ' + (level.includes('KRITICKÁ') ? 'critical' : level.includes('VYSOKÁ') ? 'high' : 'medium');
            
            document.getElementById('security-status').innerText = data.assessment.security_status || '';
            
            const score = data.assessment.sentiment_score || 0;
            document.getElementById('sentiment-score').innerText = `${score}/100`;
            document.getElementById('sentiment-bar').style.width = `${score}%`;

            // Výhled & Vyhodnocení
            if (document.getElementById('forecast-text')) {
                document.getElementById('forecast-text').innerText = data.assessment.forecast || 'Bez výhledu.';
            }
            if (document.getElementById('forecast-review-text')) {
                document.getElementById('forecast-review-text').innerText = data.assessment.forecast_review || 'Bez vyhodnocení.';
            }

            // 4. Doporučení s automatickým převedením závorek (např. Maersk) na odkazy na akcie
            const list = document.getElementById('recommendations-list');
            if (list && data.assessment.recommendations) {
                list.innerHTML = '';
                data.assessment.recommendations.forEach(rec => {
                    const li = document.createElement('li');
                    
                    // Automaticky převádí zmíněné firmy na odkazy na Yahoo Finance
                    let reasonWithLinks = rec.reason.replace(/\((např\.\vert{}například)?\s*([^)]+)\)/gi, (match, prefix, companies) => {
                        const linkedCompanies = companies.split(/,/s).map(comp => {
                            const trimmed = comp.trim();
                            if (!trimmed) return trimmed;
                            const searchUrl = `https://finance.yahoo.com/lookup?s=${encodeURIComponent(trimmed)}`;
                            return `<a href="${searchUrl}" target="_blank" class="stock-link">${trimmed}</a>`;
                        }).join(', ');
                        return `(${prefix ? prefix + ' ' : ''}${linkedCompanies})`;
                    });

                    li.innerHTML = `<strong>${rec.action}</strong> <span class="sector-tag">${rec.sector}</span>: ${reasonWithLinks}`;
                    list.appendChild(li);
                });
            }
        }

        // 5. Týdenní shrnutí
        if (data.weekly_summary) {
            document.getElementById('weekly-summary').innerText = data.weekly_summary;
        }

        // 6. Lokace zpráv s mezerami
        const locContainer = document.getElementById('locations-container');
        if (locContainer && data.locations) {
            locContainer.innerHTML = '';
            data.locations.forEach(loc => {
                const tag = document.createElement('span');
                tag.className = 'location-tag';
                tag.innerText = loc.name;
                locContainer.appendChild(tag);
            });
        }

    } catch (error) {
        console.error('Chyba při načítání data.json:', error);
    }
}

document.addEventListener('DOMContentLoaded', loadMonitorData);
