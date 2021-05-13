create or replace function top_parent(p_category_id int)
	returns text
as
$$
declare
	l_cat_name text;
begin

	with recursive categories as (
	    select  id, "name", parent_id, "level"
	    from product_category
	    where id = p_category_id
	    union all
	    select pc.id, pc.name, pc.parent_id, pc."level"
	    from categories c, product_category pc
	    where c.parent_id = pc.id
	)
	select name into l_cat_name from categories where level = 0 and parent_id is not null;

	return l_cat_name;

end;
$$ language plpgsql security definer;

