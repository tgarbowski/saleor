create or replace function sku_to_date(p_sku text)
    returns date
as
$function$
begin
    case
        when (length(p_sku) = 15) and (position('-' in p_sku) = 0) then return to_date(substring(p_sku, 5, 6), 'YYMMDD');
        when (length(p_sku) = 16) and (position('-' in p_sku) = 0) then return to_date(substring(p_sku, 4, 8), 'YYYYMMDD');
        when (length(p_sku) = 18) and (position('-' in p_sku) > 0) then return to_date(substring(p_sku, 5, 8), 'YYYYMMDD');
        else raise exception 'invalid sku format %', p_sku;
    end case;
end;
$function$ language plpgsql security definer;
