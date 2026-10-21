-- Marketing: coste de adquisición por reserva neta y cuota directa por mes (de marts_kpi). El
-- ámbito '-1' (hechos sin hotel) no es un hotel y queda fuera. completo = false: el mes aún no ha
-- madurado y sus cifras pueden cambiar; sin cierre contable, el coste de marketing y el CAC son
-- nulos.
select
    to_date(b.periodo_id, 'YYYY-MM') as mes,
    b.ambito,
    bool_and(k.completo) as completo,
    max(b.valor) filter (where b.metrica = 'comisiones') as comisiones,
    max(b.valor) filter (where b.metrica = 'coste_marketing_atribuido') as coste_marketing_atribuido,
    max(b.valor) filter (where b.metrica = 'reservas_netas') as reservas_netas,
    max(k.valor) filter (where k.kpi = 'cac_reserva_neta') as cac_reserva_neta,
    max(k.valor) filter (where k.kpi = 'cuota_directa') as cuota_directa
from {{ ref('kpi_metricas_base') }} as b
inner join {{ ref('kpi_periodo') }} as k
    on b.periodo_id = k.periodo_id and b.ambito = k.ambito and k.tipo_periodo = 'mes'
where b.ambito <> '-1'
group by b.periodo_id, b.ambito
