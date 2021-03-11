create or replace function update_prices(p_date date, p_cost_price_kg numeric)
    returns void
as $$
declare
    product_rec record;
    mnoznik decimal = 2.5;
    min_price decimal = 11.99;
    marki jsonb =
        '{
        "hugo boss" : 2,
        "armani" : 2,
        "calvin klein" : 2,
        "ralph lauren" : 2,
        "tommy hilfiger" : 2,
        "michael kors" : 2,
        "polo ralph lauren" : 2,
        "lacoste" : 2,
        "kenzo" : 2,
        "ralph lauren - polo" : 2,
        "jack wolfskin" : 2,
        "lauren ralph lauren" : 2,
        "dkny" : 2,
        "dc." : 2,
        "gucci" : 2,
        "the north face" : 1.5,
        "salomon" : 1.5,
        "abercrombie & fitch" : 1.5,
        "desigual" : 1.5,
        "nike" : 1.5,
        "levi''s" : 1.5,
        "adidas" : 1.5,
        "levi’s" : 1.5,
        "vans" : 1.5,
        "diesel" : 1.5,
        "reebok" : 1.5,
        "puma" : 1.5,
        "lego wear" : 1.5,
        "ted baker" : 1.5,
        "timberland" : 1.5,
        "tedbaker" : 1.5,
        "disney" : 1.5,
        "jack&jones" : 1.5,
        "hollister" : 1.5,
        "zara" : 1.5,
        "bench" : 1.5,
        "gap" : 1.5,
        "fruit of the loom" : 1.5,
        "abercrombie&fitch" : 1.5,
        "dorothy perkins" : 1.5,
        "regatta" : 1.5,
        "s.olivier" : 1.5,
        "converse" : 1.5,
        "lee cooper" : 1.5,
        "tom tailor" : 1.5,
        "s.oliver" : 1.5,
        "okaïdi" : 1.5
        }';
    stany jsonb =
        '{
            "nowy"           : 2,
            "nowy bez metki" : 1.5
        }';
    materialy jsonb =
        '{
            "kaszmir"           : 3,
            "jedwab"            : 2,
            "wełna"             : 1.5,
            "skóra naturalna"   : 1.5
        }';
    cost_price decimal;
    price decimal;
    marka text;
    cnt integer = 0;

begin

    raise notice '%: Start aktualizacji cen od %, cena za kg: %', now(), p_date , p_cost_price_kg;
    raise notice '---------------------------------------------';

    for product_rec in
        select pp.id, pp.name, pv.id as variant_id, pv.sku, pav."name" as marka, pav2."name" as stan, pav3."name" as material, pp.weight
        from product_product pp, product_productvariant pv,
             product_assignedproductattribute paa, product_assignedproductattribute_values paav, product_attributevalue pav, product_attribute pa,
             product_assignedproductattribute paa2, product_assignedproductattribute_values paav2, product_attributevalue pav2, product_attribute pa2,
             product_assignedproductattribute paa3, product_assignedproductattribute_values paav3, product_attributevalue pav3, product_attribute pa3
        where pp.id = pv.product_id
          and pp.id = paa.product_id
          and paa.id = paav.assignedproductattribute_id
          and paav.attributevalue_id = pav.id
          and pav.attribute_id = pa.id
          and pa."name" like 'Marka%'
          and pp.id = paa2.product_id
          and paa2.id = paav2.assignedproductattribute_id
          and paav2.attributevalue_id = pav2.id
          and pav2.attribute_id = pa2.id
          and pa2."name" = 'Stan'
          and pp.id = paa3.product_id
          and paa3.id = paav3.assignedproductattribute_id
          and paav3.attributevalue_id = pav3.id
          and pav3.attribute_id = pa3.id
          and pa3."name" = 'Materiał'
          and pp.is_published = false
          and pp.updated_at >= p_date


        loop
            if product_rec.weight is null then
                raise notice 'Waga null pomijam produkt: % %', product_rec.id, product_rec.name;
                continue;
            end if;
            cnt := cnt + 1;

            cost_price := round((product_rec.weight * (p_cost_price_kg/1000))::numeric,2);
            price := cost_price * mnoznik;

            if price < min_price then
                price := min_price;
            end if;

            price := price * coalesce((stany->>lower(product_rec.stan))::decimal,1);
            price := price * coalesce((marki->>lower(product_rec.marka))::decimal,1);
            price := price * coalesce((materialy->>lower(product_rec.material))::decimal,1);

            price := round(price,2);

            if price > 100 then
                raise notice '%;%;%;%;%;%;%',
                    product_rec.id,
                    product_rec.sku,
                    product_rec.name,
                    price,
                    product_rec.weight,
                    product_rec.stan,
                    product_rec.material;
            end if;

            begin
                update product_productvariant
                set cost_price_amount = cost_price, price_amount = price
                where id = product_rec.variant_id;
            exception when others then
                raise notice 'Błąd podczas aktualizacji ceny dla produktu % % ', product_rec.id, product_rec.name;
                raise notice '% %', SQLERRM, SQLSTATE;
            end;
        end loop;

    raise notice '---------------------------------------------';
    raise notice '%: Zaktualizowano ceny dla % produktów', now(), cnt;

end;
$$ language plpgsql security definer;
