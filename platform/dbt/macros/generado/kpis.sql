{# Generado por `atlantida-dbt generar` a partir de platform/definicion/atlantida.yml: no editar a mano. #}
{% macro metricas_base_ids() %}{{ return(['habitaciones_disponibles', 'habitaciones_disponibles_str', 'noches_vendidas', 'noches_vendidas_directo', 'ingreso_habitaciones', 'ingreso_otros', 'costes_operativos', 'comisiones', 'coste_marketing_atribuido', 'reservas_creadas', 'reservas_netas', 'reservas_llegada', 'reservas_canceladas_llegada', 'reservas_llegada_ota', 'reservas_canceladas_llegada_ota', 'ingreso_reservado', 'ingreso_cancelado', 'penalizaciones_retenidas', 'ingreso_reventa', 'promotores', 'detractores', 'respuestas_recomendacion', 'huespedes_con_estancia', 'huespedes_repetidores', 'dias_aspecto_en_rojo', 'lead_time', 'noches_por_reserva', 'noches_reservadas_directo', 'noches_captadas_ventana', 'noches_canceladas_ventana', 'ocupacion_compset', 'adr_compset', 'revpar_compset']) }}{% endmacro %}

{% macro formulas_kpi() %}{{ return({
  'ocupacion': '(1.0 * noches_vendidas / nullif(habitaciones_disponibles, 0))',
  'adr': '(1.0 * ingreso_habitaciones / nullif(noches_vendidas, 0))',
  'revpar': '(1.0 * ingreso_habitaciones / nullif(habitaciones_disponibles, 0))',
  'trevpar': '(1.0 * (ingreso_habitaciones + ingreso_otros) / nullif(habitaciones_disponibles, 0))',
  'goppar': '(1.0 * ((ingreso_habitaciones + ingreso_otros) - costes_operativos) / nullif(habitaciones_disponibles, 0))',
  'cuota_directa': '(1.0 * noches_vendidas_directo / nullif(noches_vendidas, 0))',
  'cuota_directa_captacion': '(1.0 * noches_reservadas_directo / nullif(noches_por_reserva, 0))',
  'cac_reserva_neta': '(1.0 * (comisiones + coste_marketing_atribuido) / nullif(reservas_netas, 0))',
  'tasa_cancelacion': '(1.0 * reservas_canceladas_llegada / nullif(reservas_llegada, 0))',
  'tasa_cancelacion_ota': '(1.0 * reservas_canceladas_llegada_ota / nullif(reservas_llegada_ota, 0))',
  'ingreso_perdido_neto': '(1.0 * ((ingreso_cancelado - penalizaciones_retenidas) - ingreso_reventa) / nullif(ingreso_reservado, 0))',
  'nps': '(1.0 * (100 * (promotores - detractores)) / nullif(respuestas_recomendacion, 0))',
  'tasa_repeticion': '(1.0 * huespedes_repetidores / nullif(huespedes_con_estancia, 0))',
  'dias_max_aspecto_en_rojo': 'dias_aspecto_en_rojo',
  'lead_time_medio': '(1.0 * lead_time / nullif(reservas_creadas, 0))',
  'estancia_media': '(1.0 * noches_por_reserva / nullif(reservas_netas, 0))',
  'pickup': '(noches_captadas_ventana - noches_canceladas_ventana)',
  'mpi': '(1.0 * (100 * (1.0 * noches_vendidas / nullif(habitaciones_disponibles_str, 0))) / nullif(ocupacion_compset, 0))',
  'ari': '(1.0 * (100 * (1.0 * ingreso_habitaciones / nullif(noches_vendidas, 0))) / nullif(adr_compset, 0))',
  'rgi': '(1.0 * (100 * (1.0 * ingreso_habitaciones / nullif(habitaciones_disponibles_str, 0))) / nullif(revpar_compset, 0))'
}) }}{% endmacro %}

{% macro parametros_metricas() %}{{ return({'dias_aspecto_en_rojo': {'ventana_dias': 30, 'umbral': -0.2, 'menciones_min': 8, 'hueco_max_dias': 14, 'modelo': 'clasico_lexico', 'version_modelo': '28fca1b20e5a'}}) }}{% endmacro %}

{% macro metricas_base_diarias() %}{{ return(['habitaciones_disponibles', 'habitaciones_disponibles_str', 'noches_vendidas', 'noches_vendidas_directo', 'ingreso_habitaciones', 'ingreso_otros', 'comisiones', 'coste_marketing_atribuido', 'reservas_creadas', 'reservas_netas', 'reservas_llegada', 'reservas_canceladas_llegada', 'reservas_llegada_ota', 'reservas_canceladas_llegada_ota', 'ingreso_reservado', 'ingreso_cancelado', 'penalizaciones_retenidas', 'ingreso_reventa', 'promotores', 'detractores', 'respuestas_recomendacion', 'lead_time', 'noches_por_reserva', 'noches_reservadas_directo']) }}{% endmacro %}
