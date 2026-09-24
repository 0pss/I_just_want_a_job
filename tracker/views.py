from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from .models import Application, ApplicationEvent, BlacklistEntry, CandidateProfile, EmailMessage, Job
from .services import compute_kpis, generate_document as create_document, get_active_profile, sankey_edges, trend_series

SORT_FIELDS={"score":"-llm_score","-score":"llm_score","buzzword":"-buzzword_score","-buzzword":"buzzword_score","divergence":"-score_divergence","-divergence":"score_divergence","date":"-first_seen","-date":"first_seen","company":"firma","-company":"-firma","distance":"entfernung_km","-distance":"-entfernung_km"}
def _jobs(request):
    qs=Job.objects.all(); q=request.GET.get("q","").strip()
    if q: qs=qs.filter(Q(titel__icontains=q)|Q(firma__icontains=q)|Q(beruf__icontains=q)|Q(ort__icontains=q))
    if request.GET.get("ort"): qs=qs.filter(ort=request.GET["ort"])
    if request.GET.get("status")=="unapplied": qs=qs.filter(applications__isnull=True)
    elif request.GET.get("status"): qs=qs.filter(applications__current_status=request.GET["status"])
    if request.GET.get("min_score","").isdigit(): qs=qs.filter(llm_score__gte=int(request.GET["min_score"]))
    if request.GET.get("review")=="1": qs=qs.filter(manual_review=True)
    if request.GET.get("homeoffice")=="yes": qs=qs.filter(homeoffice=True)
    if request.GET.get("homeoffice")=="no": qs=qs.filter(homeoffice=False)
    sort=request.GET.get("sort","score"); return qs.distinct().order_by(SORT_FIELDS.get(sort,"-llm_score"),"-first_seen"),sort
def dashboard(request):
    jobs,sort=_jobs(request); ctx={"page_obj":Paginator(jobs,25).get_page(request.GET.get("page",1)),"sort":sort,"kpis":compute_kpis(),"status_choices":Application.Status.choices,"distinct_orte":Job.objects.exclude(ort="").values_list("ort",flat=True).distinct().order_by("ort"),"filters":request.GET}
    if request.htmx:return render(request,"tracker/_job_table.html",ctx)
    return render(request,"tracker/dashboard.html",ctx)
job_list=dashboard
def job_detail(request,referenznummer):
    job=get_object_or_404(Job,referenznummer=referenznummer); app=job.application
    if request.method=="POST":
        action=request.POST.get("action")
        if action=="apply":
            app,created=Application.objects.get_or_create(job=job)
            if created: ApplicationEvent.objects.create(application=app,event_type=ApplicationEvent.EventType.STATUS_CHANGED,status=Application.Status.APPLIED)
        elif action=="status" and app: app.set_status(request.POST.get("status"),source=ApplicationEvent.Source.MANUAL)
        elif action=="notes" and app: app.notes=request.POST.get("notes",""); app.save(update_fields=["notes","updated_at"])
        elif action=="document": create_document(job,request.POST.get("document_type","cover_letter"),get_active_profile())
        return redirect("tracker:job_detail",referenznummer=referenznummer)
    return render(request,"tracker/job_detail.html",{"job":job,"application":app,"events":app.events.select_related("email_message").order_by("-timestamp") if app else [],"documents":job.documents.all(),"status_choices":Application.Status.choices})
def mark_applied(request,referenznummer):
    job=get_object_or_404(Job,referenznummer=referenznummer); app,created=Application.objects.get_or_create(job=job)
    if created: ApplicationEvent.objects.create(application=app,event_type=ApplicationEvent.EventType.STATUS_CHANGED,status=Application.Status.APPLIED,source=ApplicationEvent.Source.MANUAL)
    return redirect(request.META.get("HTTP_REFERER","tracker:job_list"))
def set_status(request,referenznummer):
    job=get_object_or_404(Job,referenznummer=referenznummer); app=job.application
    if app and request.POST.get("status") in Application.Status.values: app.set_status(request.POST["status"],source=ApplicationEvent.Source.MANUAL)
    return redirect("tracker:job_detail",referenznummer=referenznummer)
def generate_document(request,referenznummer):
    job=get_object_or_404(Job,referenznummer=referenznummer); create_document(job,request.POST.get("document_type","cover_letter"),get_active_profile()); return redirect("tracker:job_detail",referenznummer=referenznummer)
def application_list(request):
    qs=Application.objects.select_related("job"); q=request.GET.get("q","")
    if q: qs=qs.filter(Q(job__titel__icontains=q)|Q(job__firma__icontains=q))
    if request.GET.get("status"): qs=qs.filter(current_status=request.GET["status"])
    return render(request,"tracker/application_list.html",{"page_obj":Paginator(qs,30).get_page(request.GET.get("page",1)),"status_choices":Application.Status.choices,"filters":request.GET})
def analytics(request):
    return render(request,"tracker/analytics.html",{"kpis":compute_kpis(),"sankey":sankey_edges(),"job_trend":trend_series(Job.objects.all(),"first_seen"),"application_trend":trend_series(Application.objects.all(),"applied_at")})
def map_view(request):
    return render(request,"tracker/map.html",{"jobs_json":list(Job.objects.filter(latitude__isnull=False,longitude__isnull=False).values("referenznummer","titel","firma","ort","latitude","longitude","llm_score","manual_review"))})
def email_list(request):
    qs=EmailMessage.objects.select_related("application"); q=request.GET.get("q","")
    if q: qs=qs.filter(Q(sender__icontains=q)|Q(subject__icontains=q)|Q(body_text__icontains=q))
    return render(request,"tracker/email_list.html",{"emails":Paginator(qs,40).get_page(request.GET.get("page",1))})
def settings_view(request):
    if request.method=="POST":
        if request.POST.get("action")=="blacklist":
            term=request.POST.get("term","").strip()
            if term: BlacklistEntry.objects.get_or_create(term=term,defaults={"reason":request.POST.get("reason","").strip()})
        elif request.POST.get("action")=="profile":
            CandidateProfile.objects.filter(active=True).update(active=False); last=CandidateProfile.objects.order_by("-version").first()
            CandidateProfile.objects.create(name=request.POST.get("name","Candidate"),profile_text=request.POST.get("profile_text",""),version=(last.version+1 if last else 1),active=True)
        return redirect("tracker:settings")
    return render(request,"tracker/settings.html",{"blacklist":BlacklistEntry.objects.all(),"profiles":CandidateProfile.objects.all(),"active_profile":CandidateProfile.objects.filter(active=True).first()})
def delete_blacklist_entry(request,pk):
    get_object_or_404(BlacklistEntry,pk=pk).delete(); return redirect("tracker:settings")
