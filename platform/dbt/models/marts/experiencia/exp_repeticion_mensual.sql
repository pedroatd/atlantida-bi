-- Experiencia y marketing: repetición mensual sobre el golden record, solo titulares (de
-- marts_kpi). El ámbito '-1' (hechos sin hotel) no es un hotel y queda fuera.
select
    to_date(b.periodo_id, 'YYYY-MM') as mes,
    b.ambito,
    max(b.valor) filter (where b.metrica = 'huespedes_con_estancia') as huespedes_con_estancia,
    max(b.valor) filter (where b.metrica = 'huespedes_repetidores') as huespedes_repetidores,
    max(k.valor) filter (where k.kpi = 'tasa_repeticion') as tasa_repeticion
from {{ ref('kpi_metricas_base') }} as b
inner join {{ ref('kpi_periodo') }} as k
    on b.periodo_id = k.periodo_id and b.ambito = k.ambito and k.tipo_periodo = 'mes'
where b.ambito <> '-1'
group by b.periodo_id, b.ambito
