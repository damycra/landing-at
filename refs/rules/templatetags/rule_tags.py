from django import template

register = template.Library()

@register.inclusion_tag('rules/pagegroup_summary.html')
def pagegroup_summary(page_group, colour):
    return {'page_group': page_group, 'colour':colour}

@register.inclusion_tag('rules/rules/rule_summary.html', takes_context=True)
def rule_summary(context):    
    return {'rule': context['rule'],
            'user_perms': context['user_perms'],
            'MEDIA_URL': context.get('MEDIA_URL', '')}

@register.inclusion_tag('rules/filters/filter_summary.html', takes_context=True)
def filter_summary(context):    
    filter_hits = context.get('filter_hits', {})
    filter = context['filter']
    total = 0
    fhits = []
    for i in filter_hits.get(filter.id, [])[-14:]:
        total = total + i
        fhits.append(str(i))
    return {'filter': filter,
            'user_perms': context['user_perms'],
            'MEDIA_URL': context.get('MEDIA_URL', ''),
            'filter_hits': ','.join(fhits), 
            'total_for_period': total}

@register.inclusion_tag('rules/locationgroup_summary.html')
def locationgroup_summary(location_group):    
    return {'location_group': location_group}
