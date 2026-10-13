from django.urls import path

from . import views

urlpatterns = [
    path("", views.search, name="search"),
    path("models/", views.model_choices, name="model_choices"),
    path("model/<path:model_name>/", views.model_listings, name="model_listings"),
    path("card/<int:pk>/", views.card_listings, name="card_listings"),
    path("go/<int:pk>/", views.outbound, name="outbound"),
]
