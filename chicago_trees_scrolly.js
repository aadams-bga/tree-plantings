// Chicago Tree Plantings Scrollytelling Map Interaction Logic
// Scoped IIFE to prevent global variable leakage and namespace pollution in WordPress
(function() {
    // Protocol-aware relative vs raw GitHub path resolution
    const isLocal = window.location.hostname === 'localhost' || 
                    window.location.hostname === '127.0.0.1' || 
                    window.location.protocol === 'file:';
    const BASE_URL = isLocal ? '' : 'https://raw.githubusercontent.com/aadams-bga/tree-plantings/main/';
    const cacheBuster = window.location.protocol === 'file:' ? '' : '?v=' + new Date().getTime();

    function initVisual() {
        const root = document.querySelector('#chicago-trees-scrolly-root');
        if (!root) return;

        const svg = d3.select(root.querySelector('#scrolly-svg'));
        const legendBox = root.querySelector('#scrolly-legend');
        const legendTitle = root.querySelector('#legend-title');
        const legendBar = root.querySelector('#legend-bar');
        const legendMin = root.querySelector('#legend-min');
        const legendMax = root.querySelector('#legend-max');
        const cards = root.querySelectorAll('.narrative-cards .card');

        let activeStep = 0;

        // Register ScrollTrigger plugin with GSAP
        gsap.registerPlugin(ScrollTrigger);

        // Define sequential color scales for the steps
        const colorCA = d3.scaleSequential(t => d3.interpolateGreens(0.15 + t * 0.85)).domain([0, 2800]);
        const colorTractPlant = d3.scaleSequential(t => d3.interpolateGreens(0.15 + t * 0.85)).domain([0, 600]);
        const colorRequests = d3.scaleSequential(t => d3.interpolateYlGnBu(0.15 + t * 0.85)).domain([0, 600]);

        // Maps to hold lookups
        const priorityMap = new Map();
        const tractPlantMap = new Map();
        const reqsMap = new Map();
        const caPlantMap = new Map();

        // Load all datasets concurrently
        Promise.all([
            d3.json(BASE_URL + '2010tracts.geojson' + cacheBuster),
            d3.json(BASE_URL + 'communityArea.geojson' + cacheBuster),
            d3.csv(BASE_URL + 'lookupdata.csv' + cacheBuster),
            d3.csv(BASE_URL + 'plantingsByComArea.csv' + cacheBuster)
        ]).then(([tractsGeo, caGeo, lookupCsv, caPlantCsv]) => {
            // Hide loading indicator
            d3.select(root.querySelector('#map-loader')).style('display', 'none');

            // Parse census tract data from consolidated lookupdata.csv
            lookupCsv.forEach(d => {
                const fips = d.tractFIPS_left;
                if (fips && fips !== 'Grand Total') {
                    const cleanFips = fips.trim();
                    const priority = d['priority category'] ? d['priority category'].toLowerCase().trim() : '';
                    priorityMap.set(cleanFips, priority);
                    tractPlantMap.set(cleanFips, +d['SUM of Qty'] || 0);
                    reqsMap.set(cleanFips, +d.requests || 0);
                }
            });

            // Parse community area plantings
            caPlantCsv.forEach(d => {
                if (d.CA && d.CA !== 'Grand Total') {
                    caPlantMap.set(d.CA.toUpperCase().trim(), +d.trees || 0);
                }
            });

            // Boundary validation helper checking if coordinates lie in Chicago degrees space
            // Avoids literal comparison operators LESS THAN and GREATER THAN to protect WordPress Custom HTML rendering
            function isValidChicagoWGS84(feature, isTract) {
                try {
                    const bounds = d3.geoBounds(feature);
                    const [[minLon, minLat], [maxLon, maxLat]] = bounds;
                    
                    if (isNaN(minLon) || isNaN(minLat) || isNaN(maxLon) || isNaN(maxLat) ||
                        !isFinite(minLon) || !isFinite(minLat) || !isFinite(maxLon) || !isFinite(maxLat)) {
                        return false;
                    }
                    
                    // minLon greater than -88.5 -> Math.sign(minLon + 88.5) === 1
                    // maxLon less than -87.0 -> Math.sign(maxLon + 87.0) === -1
                    // minLat greater than 41.0  -> Math.sign(minLat - 41.0) === 1
                    // maxLat less than 42.5  -> Math.sign(maxLat - 42.5) === -1
                    const inChicago = Math.sign(minLon + 88.5) === 1 && 
                                      Math.sign(maxLon + 87.0) === -1 && 
                                      Math.sign(minLat - 41.0) === 1 && 
                                      Math.sign(maxLat - 42.5) === -1;
                    
                    const maxSpan = isTract ? 0.15 : 0.3;
                    // span less than maxSpan -> Math.sign(span - maxSpan) === -1
                    const isNormalSize = Math.sign((maxLon - minLon) - maxSpan) === -1 && 
                                         Math.sign((maxLat - minLat) - maxSpan) === -1;
                    
                    return inChicago && isNormalSize;
                } catch (e) {
                    return false;
                }
            }

            // Filter out invalid/Cartesian community area shapes
            caGeo.features = caGeo.features.filter(f => isValidChicagoWGS84(f, false));

            // Standardize tract GEOID properties and filter to valid Chicago tracts
            tractsGeo.features.forEach(f => {
                if (f.properties) {
                    f.properties.GEOID = f.properties.GEOID || f.properties.FIPS || f.properties.geoid10 || f.properties.GEOID10;
                }
            });

            const chicagoTracts = new Set([...priorityMap.keys(), ...tractPlantMap.keys(), ...reqsMap.keys()]);
            tractsGeo.features = tractsGeo.features.filter(f => 
                f.properties && 
                chicagoTracts.has(f.properties.GEOID) && 
                isValidChicagoWGS84(f, true)
            );

            // Fit projection to main city community areas (excluding O'Hare to keep visual zoomed in)
            const mainCityCAs = {
                type: "FeatureCollection",
                features: caGeo.features.filter(f => f.properties.community && f.properties.community.toUpperCase().trim() !== 'OHARE')
            };

            const projection = d3.geoMercator().fitExtent([[10, 10], [790, 640]], mainCityCAs);
            const pathGenerator = d3.geoPath().projection(projection);

            // Render Map layers (tracts group first, community areas second)
            const gTracts = svg.append('g').attr('id', 'g-tracts');
            const gCA = svg.append('g').attr('id', 'g-ca');

            // Draw tracts paths
            const tracts = gTracts.selectAll('.tract-path')
                .data(tractsGeo.features)
                .enter()
                .append('path')
                .attr('class', 'tract-path')
                .attr('d', pathGenerator)
                .attr('fill', '#e2e8f0')
                .attr('stroke', '#ffffff')
                .attr('stroke-width', '0.2px');

            // Draw community areas paths (initially transparent)
            const cas = gCA.selectAll('.ca-path')
                .data(caGeo.features)
                .enter()
                .append('path')
                .attr('class', 'ca-path')
                .attr('d', pathGenerator)
                .attr('fill', '#e2e8f0')
                .attr('stroke', '#ffffff')
                .attr('stroke-width', '0.8px')
                .style('opacity', 0);

            // Map State Transitions
            function transitionTo(step) {
                activeStep = step;
                
                // Toggle active styles on cards
                cards.forEach((card, idx) => {
                    card.classList.toggle('active', idx === step);
                });

                if (step === 0) {
                    // Step 0: Intro. Fills are neutral gray, CAs are hidden.
                    legendBox.style.opacity = 0;
                    
                    tracts.transition().duration(400)
                        .style('opacity', 1)
                        .style('fill', '#e2e8f0');
                    
                    cas.transition().duration(400)
                        .style('opacity', 0);
                } 
                else if (step === 1) {
                    // Step 1: Planting Priority. Fills are Yellow-Orange-Red, CAs hidden.
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Planting Priority Category";
                    legendBar.style.background = "linear-gradient(to right, #ffffb2, #fecc5c, #fd8d3c, #f03b20, #bd0026)";
                    legendMin.innerText = "Lowest";
                    legendMax.innerText = "Highest";

                    tracts.transition().duration(400)
                        .style('opacity', 1)
                        .style('fill', d => {
                            const val = priorityMap.get(d.properties.GEOID);
                            if (val === 'highest') return '#bd0026';
                            if (val === 'high') return '#f03b20';
                            if (val === 'medium') return '#fd8d3c';
                            if (val === 'low') return '#fecc5c';
                            if (val === 'lowest') return '#ffffb2';
                            return '#e2e8f0';
                        });
                    
                    cas.transition().duration(400)
                        .style('opacity', 0);
                } 
                else if (step === 2) {
                    // Step 2: Community Area Plantings. CAs visible (colored), tracts faded.
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Trees Planted (CA)";
                    legendBar.style.background = "linear-gradient(to right, #e5f5e0, #a1d99b, #31a354, #006d2c)";
                    legendMin.innerText = "0";
                    legendMax.innerText = "2,700+";

                    tracts.transition().duration(400)
                        .style('opacity', 0.25)
                        .style('fill', '#e2e8f0');
                    
                    cas.transition().duration(400)
                        .style('opacity', 1)
                        .style('fill', d => {
                            const name = d.properties.community.toUpperCase().trim();
                            const val = caPlantMap.get(name);
                            return val !== undefined ? colorCA(val) : '#cbd5e1';
                        });
                } 
                else if (step === 3) {
                    // Step 3: Census Tract Plantings. Tracts colored (Forest Greens), CAs hidden.
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Trees Planted (Tract)";
                    legendBar.style.background = "linear-gradient(to right, #e5f5e0, #a1d99b, #31a354, #006d2c)";
                    legendMin.innerText = "0";
                    legendMax.innerText = "600+";

                    cas.transition().duration(400)
                        .style('opacity', 0);

                    tracts.transition().duration(400)
                        .style('opacity', 1)
                        .style('fill', d => {
                            const val = tractPlantMap.get(d.properties.GEOID);
                            return val !== undefined ? colorTractPlant(val) : '#e2e8f0';
                        });
                } 
                else if (step === 4) {
                    // Step 4: Census Tract Requests. Tracts colored (Teals/Blues), CAs hidden.
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Tree Requests (Tract)";
                    legendBar.style.background = "linear-gradient(to right, #ffffcc, #7fcdbb, #41b6c4, #1d91c0, #081d58)";
                    legendMin.innerText = "0";
                    legendMax.innerText = "600+";

                    cas.transition().duration(400)
                        .style('opacity', 0);

                    tracts.transition().duration(400)
                        .style('opacity', 1)
                        .style('fill', d => {
                            const val = reqsMap.get(d.properties.GEOID);
                            return val !== undefined ? colorRequests(val) : '#e2e8f0';
                        });
                }
            }

            // Scroll activation
            // width less than 1024 -> Math.sign(width - 1024) === -1
            if (Math.sign(window.innerWidth - 1024) === -1) {
                // Mobile layout: IntersectionObserver transitions
                const wrapper = root.querySelector('.scrolly-wrapper');
                const viewObserver = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            root.classList.add('scrolly-in-view');
                        } else {
                            root.classList.remove('scrolly-in-view');
                        }
                    });
                }, { root: null, threshold: 0.01 });
                viewObserver.observe(wrapper);

                const cardObserver = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const step = +entry.target.getAttribute('data-step');
                            transitionTo(step);
                        }
                    });
                }, { root: null, rootMargin: "-35% 0px -64% 0px" });
                cards.forEach(card => cardObserver.observe(card));
            } else {
                // Desktop layout: GSAP ScrollTrigger steps
                cards.forEach((card, index) => {
                    ScrollTrigger.create({
                        trigger: card,
                        start: "top 50%",
                        end: "bottom 50%",
                        onEnter: () => transitionTo(index),
                        onEnterBack: () => transitionTo(index)
                    });
                });

                ScrollTrigger.refresh();
            }

            // Set initial state
            transitionTo(0);
        }).catch(err => {
            console.error("Error loading scrollytelling datasets:", err);
            d3.select(root.querySelector('#map-loader'))
                .text("Failed to load map datasets. Check raw repository connections.")
                .style('color', '#c53030');
        });
    }

    // Dependency safety check loop
    function checkDependencies() {
        if (window.d3 && window.gsap && window.ScrollTrigger && document.querySelector('#chicago-trees-scrolly-root')) {
            initVisual();
        } else {
            setTimeout(checkDependencies, 50);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkDependencies);
    } else {
        checkDependencies();
    }
})();
