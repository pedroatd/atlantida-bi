-- Huéspedes de cada reserva (reservation_guest): el titular y sus acompañantes.
select
    reservation_id as reserva_id,
    guest_id as huesped_id,
    {{ traducir('role', {'holder': 'titular', 'companion': 'acompanante'}) }} as rol,
    coalesce(role = 'holder', false) as es_titular,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'reservation_guest') }}
