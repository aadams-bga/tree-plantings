// Scoped IIFE to prevent variable leaks and namespace conflicts
(function() {
    // Determine if running locally to use relative paths for easier testing
    const isLocal = window.location.hostname === 'localhost' || 
                    window.location.hostname === '127.0.0.1' || 
                    window.location.protocol === 'file:';
    const BASE_URL = isLocal ? '' : 'https://raw.githubusercontent.com/aadams-bga/tree-plantings/main/';

    // Initialization logic
    function initVisual() {
        const root = document.querySelector('#chicago-trees-scrolly-root');
        if (!root) return; // Prevent errors if injected element isn't in DOM yet

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

        // Define thematic D3 sequential color scales
        // Priority: Rank 1 is highest priority (Red), Rank 787 is lowest (Light Yellow)
        const colorPriority = d3.scaleSequential(d3.interpolateYlOrRd).domain([787, 1]);
        // Community Area Plantings: Forest Green scale from 0 to 2800
        const colorCA = d3.scaleSequential(d3.interpolateGreens).domain([0, 2800]);
        // Tract Plantings: Forest Green scale from 0 to 650
        const colorTractPlant = d3.scaleSequential(d3.interpolateGreens).domain([0, 650]);
        // Requests: Green-to-Blue/Teal scale from 0 to 650
        const colorRequests = d3.scaleSequential(d3.interpolateYlGnBu).domain([-50, 650]);

        // Data storage
        const priorityMap = new Map();
        const caPlantMap = new Map();
        const tractPlantMap = new Map();
        const reqsMap = new Map();

        // Load all geojson and CSV data
        Promise.all([
            d3.json(BASE_URL + 'tracts.geojson'),
            d3.json(BASE_URL + 'communityArea.geojson'),
            d3.csv(BASE_URL + 'priorityByCensusTract.csv'),
            d3.csv(BASE_URL + 'plantingsByComArea.csv'),
            d3.csv(BASE_URL + 'plantingsbyCensusTract.csv'),
            d3.csv(BASE_URL + 'reqsByCensusTract.csv')
        ]).then(([tractsGeo, caGeo, priorityCsv, caPlantCsv, tractPlantCsv, reqsCsv]) => {
            
            // 1. Process lookup maps, filtering totals/Grand Totals
            priorityCsv.forEach(d => {
                if (d.tractFIPS && d.priority && d.tractFIPS !== 'Grand Total') {
                    priorityMap.set(d.tractFIPS, +d.priority);
                }
            });

            caPlantCsv.forEach(d => {
                if (d.CA && d.CA !== 'Grand Total') {
                    caPlantMap.set(d.CA.toUpperCase().trim(), +d.trees);
                }
            });

            tractPlantCsv.forEach(d => {
                if (d.tractFIPS && d.tractFIPS !== 'Grand Total') {
                    const qty = +d.SUM_of_Qty || +d['SUM of Qty'] || 0;
                    tractPlantMap.set(d.tractFIPS, qty);
                }
            });

            reqsCsv.forEach(d => {
                if (d.tractFIPS && d.tractFIPS !== 'Grand Total') {
                    reqsMap.set(d.tractFIPS, +d.reqs);
                }
            });

            // 2. Performance Optimization: Filter state-wide tracts to just Chicago
            const chicagoTracts = new Set([
                ...priorityMap.keys(),
                ...tractPlantMap.keys(),
                ...reqsMap.keys()
            ]);
            tractsGeo.features = tractsGeo.features.filter(f => chicagoTracts.has(f.properties.GEOID || f.properties.FIPS));

            // 3. Setup Projection fit to Chicago Core community areas (excluding O'Hare) to zoom/crop the map
            const mainCityCAs = {
                type: "FeatureCollection",
                features: caGeo.features.filter(f => f.properties.community && f.properties.community.toUpperCase().trim() !== 'OHARE')
            };
            const projection = d3.geoMercator().fitSize([800, 650], mainCityCAs);
            const pathGenerator = d3.geoPath().projection(projection);

            // 4. Render Map layers
            const gCA = svg.append('g').attr('id', 'g-ca');
            const gTracts = svg.append('g').attr('id', 'g-tracts');

            // Render Tracts
            const tracts = gTracts.selectAll('.tract-path')
                .data(tractsGeo.features)
                .enter()
                .append('path')
                .attr('class', 'tract-path')
                .attr('d', pathGenerator)
                .attr('stroke', '#ffffff')
                .attr('stroke-width', '0.2px')
                .attr('fill', '#e8e8e8')
                .style('transition', 'fill 0.4s ease, stroke 0.4s ease');

            // Render Community Areas (styled initially transparent)
            const cas = gCA.selectAll('.ca-path')
                .data(caGeo.features)
                .enter()
                .append('path')
                .attr('class', 'ca-path')
                .attr('d', pathGenerator)
                .attr('stroke', '#ffffff')
                .attr('stroke-width', '0.8px')
                .attr('fill', '#e8e8e8')
                .style('opacity', 0)
                .style('transition', 'fill 0.4s ease, stroke 0.4s ease, opacity 0.4s ease');

            // 5. Tooltip interaction logic (Removed)

            // 6. Map State Transitions
            function transitionTo(step) {
                activeStep = step;
                
                // Highlight active card
                cards.forEach((card, idx) => {
                    card.classList.toggle('active', idx === step);
                });

                // State-specific layout modifications
                if (step === 0) {
                    // Intro state: Neutral grey base map
                    legendBox.style.opacity = 0;
                    
                    tracts.style('opacity', 1)
                          .style('fill', '#e8e8e8')
                          .attr('stroke-width', '0.2px');
                    cas.style('opacity', 0);
                } 
                else if (step === 1) {
                    // Priority Rank state
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Planting Priority Rank";
                    legendBar.style.background = "linear-gradient(to right, #ffeda0, #feb24c, #f03b20)";
                    legendMin.innerText = "Lowest (787)";
                    legendMax.innerText = "Highest (1)";

                    tracts.style('opacity', 1)
                          .style('fill', d => {
                              const val = priorityMap.get(d.properties.GEOID || d.properties.FIPS);
                              return val ? colorPriority(val) : '#f0f0f0';
                          })
                          .attr('stroke-width', '0.1px');
                    cas.style('opacity', 0);
                } 
                else if (step === 2) {
                    // Community Area Plantings state
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Trees Planted (CA)";
                    legendBar.style.background = "linear-gradient(to right, #e5f5e0, #a1d99b, #31a354, #006d2c)";
                    legendMin.innerText = "0";
                    legendMax.innerText = "2,700+";

                    tracts.style('opacity', 0.25)
                          .style('fill', '#e8e8e8')
                          .attr('stroke-width', '0.1px');
                    
                    cas.style('opacity', 1)
                       .style('fill', d => {
                           const name = d.properties.community.toUpperCase().trim();
                           const val = caPlantMap.get(name);
                           return val ? colorCA(val) : '#f0f0f0';
                       });
                } 
                else if (step === 3) {
                    // Census Tract Plantings state
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Trees Planted (Tract)";
                    legendBar.style.background = "linear-gradient(to right, #e5f5e0, #a1d99b, #31a354, #006d2c)";
                    legendMin.innerText = "0";
                    legendMax.innerText = "600+";

                    cas.style('opacity', 0);

                    tracts.style('opacity', 1)
                          .style('fill', d => {
                              const val = tractPlantMap.get(d.properties.GEOID || d.properties.FIPS);
                              return val ? colorTractPlant(val) : '#f5f5f5';
                          })
                          .attr('stroke-width', '0.1px');
                } 
                else if (step === 4) {
                    // Requests state (unified to Forest Green scale)
                    legendBox.style.opacity = 1;
                    legendTitle.innerText = "Tree requests (Tract)";
                    legendBar.style.background = "linear-gradient(to right, #e5f5e0, #a1d99b, #31a354, #006d2c)";
                    legendMin.innerText = "0";
                    legendMax.innerText = "600+";

                    cas.style('opacity', 0);

                    tracts.style('opacity', 1)
                          .style('fill', d => {
                              const val = reqsMap.get(d.properties.GEOID || d.properties.FIPS);
                              return val ? colorTractPlant(val) : '#f5f5f5';
                          })
                          .attr('stroke-width', '0.1px');
                }
            }

            // 7. Initialize triggers: IntersectionObserver on mobile, GSAP on desktop
            if (window.innerWidth < 1024) {
                // Mobile layout - IntersectionObserver to toggle fixed bottom state
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

                // Mobile layout - IntersectionObserver for card transitions
                // Triggers exactly as each card enters the reading zone at 35% from top of screen
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
                // Desktop layout - GSAP ScrollTriggers for transition steps
                cards.forEach((card, index) => {
                    ScrollTrigger.create({
                        trigger: card,
                        start: "top 50%",
                        end: "bottom 50%",
                        onEnter: () => transitionTo(index),
                        onEnterBack: () => transitionTo(index),
                    });
                });

                // Note: Pinning is handled via CSS position: sticky on .graphic-pane for desktop layout.
            }

            // Render initial state
            transitionTo(0);

            // Recalculate ScrollTrigger coordinates on desktop
            if (window.innerWidth >= 1024) {
                ScrollTrigger.refresh();
            }
        }).catch(err => {
            console.error("Error loading scrollytelling datasets:", err);
        });
    }

    // Safety check loop to ensure D3, GSAP/ScrollTrigger, and the DOM container are all ready
    function checkDependencies() {
        if (window.d3 && window.gsap && window.ScrollTrigger && document.querySelector('#chicago-trees-scrolly-root')) {
            initVisual();
        } else {
            setTimeout(checkDependencies, 50); // Check again in 50ms
        }
    }

    // Begin check sequence once document ready state is resolved
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', checkDependencies);
    } else {
        checkDependencies();
    }
})();
