from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

def get_paginated_data(request, queryset, default_limit=10, unique_id=None):
    # Retrieve the limit parameter, adding the unique_id if provided
    limit_param = 'limit' + str(unique_id) if unique_id else 'limit'
    page_param = 'page' + str(unique_id) if unique_id else 'page'
    
    limit = request.GET.get(limit_param, str(default_limit))
    
    if limit == 'all':
        # Use an arbitrarily large limit to display all items
        limit = 1000000
    else:
        try:
            limit = int(limit)
            if limit <= 0:
                limit = default_limit
        except (ValueError, TypeError):
            limit = default_limit

    paginator = Paginator(queryset, limit)
    page = request.GET.get(page_param, '1')
    
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
        
    return paginator, page_obj
