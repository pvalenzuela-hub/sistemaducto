const listacuentasocios = async () =>{
	try {
		const response = await fetch("./seriesocios");
		const data = await response.json();
		//console.log(data);
		return data; // Retornamos directamente los datos de donaciones
		
	} catch (error) {
		console.log(error);
	}
};

const listadonaciones = async () =>{
	try {
		const response = await fetch("./seriedonaciones");
		const data = await response.json();
		//console.log(data);
		return data; // Retornamos directamente los datos de donaciones
		
	} catch (error) {
		console.log(error);
	}
};

const initChart = async () => {
    const myChart = echarts.init(document.getElementById("chart"));
    
    myChart.setOption(await listadonaciones());

	const myChart2 = echarts.init(document.getElementById("chart2"));

	myChart2.setOption(await listacuentasocios());
	
    myChart.resize();
	myChart2.resize();
};

window.addEventListener("load", async () => {
    await initChart();
});