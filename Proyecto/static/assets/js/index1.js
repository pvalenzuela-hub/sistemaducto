const listadonaciones = async () =>{
	try {
		const response = await fetch("./seriedonaciones");
		const data = await response.json();
		console.log(data);
		return data; // Retornamos directamente los datos de donaciones
		
	} catch (error) {
		console.log(error);
	}
}
$(function(e) {

    /*-----echart1-----*/
	
	var chart;
	//var lectura
	
	seriedatos = [50000, 30000, 10000, 25000, 30000,8000];
	const updateDonacionesSeries = async () => {
        const data = await listadonaciones();
		chart = new ApexCharts(document.querySelector("#chartArea"), data);

        // Obtener la serie "Donaciones" del objeto de opciones del gráfico
		//console.log(Object.values(data))
		//donor = data.map(elemento => Object.entries(elemento));
		//console.log(donor.total)
		//lectura = data
		//console.log(lectura)

		// donor = JSON.parse(data);
		// for (var i = 0; i < donor.donaciones.length; i++) {
		// 	var fila = donor.donaciones[i];
		// 	console.log(fila.total);
		// }


		//console.log(Object.entries(data));
		//console.log(options)
        //const donacionesSeries = options.series.find(series => series.name === "Donaciones");
		//console.log(donacionesSeries)

        // Asignar los nuevos datos a la propiedad 'data' de la serie "Donaciones"
        //donacionesSeries.data = array;
		//console.log(Object.values(data))
        // Renderizar el gráfico nuevamente para reflejar los cambios
        //chart.render();
    };
	
	
	// Llamar a la función para actualizar los datos de la serie "Donaciones"
	updateDonacionesSeries();
	
	//var options = lectura
	
	//console.log(data)
	var options = {
		chart: {
			height: 300,
			type: "line",
			stacked: false,
			toolbar: {
				enabled: false
			},
			dropShadow: {
				enabled: true,
				opacity: 0.1,
			},
		},
		colors: ["#6259ca", "#f99433", 'rgba(119, 119, 142, 0.05)'],
		dataLabels: {
			enabled: false
		},
		stroke: {
			curve: "smooth",
			width: [3, 3, 0],
			dashArray: [0, 4],
			lineCap: "round"
		},
		grid: {
			padding: {
				left: 0,
				right: 0
			},
			strokeDashArray: 3
		},
		markers: {
			size: 0,
			hover: {
				size: 0
			}
		},
		series: [{
			name: "Donaciones",
			type: 'line',
			//data: [0, 10000, 5000, 3000, 2000, 5000, 6000, 2000, 5000, 2000, 5000, 30000]
			data: seriedatos
			
		},{
			name: "Socios Totales",
			type: 'line',
			data: [0, 2, 5, 10, 20, 30]
		}],
		xaxis: {
			type: "month",
			categories: ["Ene", "Feb", "Mar", "Abr", "May", "Jun"],
			axisBorder: {
				show: false,
				color: 'rgba(119, 119, 142, 0.08)',
			},
			labels: {
				style: {
					color: '#8492a6',
					fontSize: '12px',
				},
			},
		},
		yaxis: {
			labels: {
				style: {
					color: '#8492a6',
					fontSize: '12px',
				},
			},
			axisBorder: {
				show: false,
				color: 'rgba(119, 119, 142, 0.08)',
			},
		},
		fill: {
			gradient: {
			  inverseColors: false,
			  shade: 'light',
			  type: "vertical",
			  opacityFrom: 0.85,
			  opacityTo: 0.55,
			  stops: [0, 100, 100, 100]
			}
		  },
		tooltip: {
			show:false
		},
		legend: {
			position: "top",
			show:true
		}
	}

	console.log(options)
	var chart = new ApexCharts(document.querySelector("#chartArea"), options);
	
	
	chart.render();


	var options = {
		chart: {
		height: 305,
		type: 'radialBar',
		offsetX: 0,
		offsetY: 10,
	},
	plotOptions: {
	    radialBar: {
		startAngle: -135,
		endAngle: 135,
		size: 120,
		imageWidth: 50,
        imageHeight: 50,
		track: {	
			strokeWidth: "80%",	
		},
		dropShadow: {
			enabled: false,
			top: 0,
			left: 0,
			bottom: 0,
			blur: 3,
			opacity: 0.5
		},
		dataLabels: {
		  name: {
			fontSize: '16px',
			color: undefined,
			offsetY: 30,
		  },
		  hollow: {	
			 size: "60%"	
			},
		  value: {
			offsetY: -10,
			fontSize: '22px',
			color: undefined,
			formatter: function (val) {
			  return val + "%";
			}
		  }
		}
	  }
	},
	colors: ['#ff5d9e'],
	fill: {
		type: "gradient",
		gradient: {
			shade: "gradient",
			type: "horizontal",
			shadeIntensity: .5,
			gradientToColors: ['#6259ca'],
			inverseColors: !0,
			opacityFrom: 1,
			opacityTo: 1,
			stops: [0, 100]
		}
	},
	stroke: {
		dashArray: 4
	},
	series: [83],	
		labels: [""]
	};

	var chart = new ApexCharts(document.querySelector("#recentorders"), options);
	chart.render();
	


	//______Data-Table
	$('#data-table').DataTable({
		language: {
			searchPlaceholder: 'Search...',
			sSearch: '',
		}
	});
	
	//______Select2 
	$('.select2').select2({
		minimumResultsForSearch: Infinity
	});

	
	
 });
 
 