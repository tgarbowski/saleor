create or replace function generate_bundle_content(p_sku text)
	returns jsonb
as
$$
declare
	l_bundle_content jsonb;
begin

	with megapaka_stats as (
		select	top_parent(pp.category_id) kategoria, count(*) ilosc, (sum(pp.weight)/1000)::numeric as waga
		from product_product pp
		where pp.metadata->>'bundle.id' = p_sku
		group by 1
		order by 2 desc, 1
	)
	select json_agg(json_build_array(kategoria,ilosc,waga,null))::jsonb into l_bundle_content from megapaka_stats;

	return l_bundle_content;

end;
$$ language plpgsql security definer;

