from datetime import timedelta, date

def calcular_dias_habiles_vacaciones(fecha_inicio, fecha_fin):
    dias_habiles = 0
    dia = fecha_inicio

    while dia <= fecha_fin:
        if dia.weekday() < 5:  # Verificar si es un día de lunes a viernes
            dias_habiles += 1
        dia += timedelta(days=1)

    return dias_habiles

