{% for filter in filters %}
try {
(function(msg, elemId, name, trackMethod){
{% if filter.code %}{{ filter.code|safe }}{% else %}_landingAt.show(msg, elemId){% endif %};
_landingAt.gaTrack(name, trackMethod);})("{{ filter.html|escapejs }}","{{ filter.container_element_id }}","{{ filter.name|escapejs }}","{{ filter.tracking_method }}" );
}catch(err){}
{% endfor %} 
