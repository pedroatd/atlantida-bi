select
    payment_id as pago_id,
    reservation_id as reserva_id,
    paid_at as pagado_en,
    {{ fecha_local('paid_at') }} as fecha_pago,
    amount as importe,
    {{ traducir('payment_type', {'deposit': 'deposito', 'balance': 'saldo', 'refund': 'devolucion'}) }} as tipo_pago,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'payment') }}
