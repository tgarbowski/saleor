create or replace function archive_products(dt_from date, dt_to date)
    returns bigint
as
$$
declare
  cnt bigint = 0;
  r product_product%rowtype;
begin
    for r in
        select * from product_product
        where Cast(private_metadata->>'publish.status.date' as DATE)::timestamp between dt_from and dt_to
        and private_metadata->>'publish.allegro.status' = 'sold'
        and length(coalesce(metadata->>'bundle.id','')) = 0
    loop
        cnt := cnt + 1;
        insert into arch_product_product select(r).*;
        insert into arch_product_productvariant select * from product_productvariant pv where pv.product_id = r.id;
        insert into arch_product_productmedia select * from product_productmedia ppi where ppi.product_id = r.id;
    end loop;
    return cnt;
end;
$$ language plpgsql security definer;
