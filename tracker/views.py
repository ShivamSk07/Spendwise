from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from .models import Expense, Budget, Profile
from .forms import ExpenseForm, BudgetForm, UserUpdateForm, ProfileUpdateForm
import csv

@login_required
def profile(request):
    profile_obj, created = Profile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=profile_obj)
        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            messages.success(request, f'Your account has been updated!')
            return redirect('profile')
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=profile_obj)

    context = {
        'u_form': u_form,
        'p_form': p_form
    }

    return render(request, 'profile.html', context)
from django.http import HttpResponse
from datetime import datetime


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful. Welcome!")
            return redirect('dashboard')
    else:
        form = UserCreationForm()
    return render(request, 'register.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('login')



@login_required
def dashboard(request):
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    expenses = Expense.objects.filter(
        user=request.user, 
        date__month=current_month, 
        date__year=current_year
    ).order_by('-date')
    
    total_spent = expenses.aggregate(Sum('amount'))['amount__sum'] or 0
    

    budget, created = Budget.objects.get_or_create(
        user=request.user, 
        month=current_month, 
        year=current_year,
        defaults={'amount': 0}
    )
    
    
    categories_data = list(expenses.values('category').annotate(total=Sum('amount')).order_by('-total'))
    
    context = {
        'total_spent': total_spent,
        'budget': budget,
        'remaining': budget.amount - total_spent if budget.amount > 0 else 0,
        'recent_expenses': expenses[:5],
        'categories_data': categories_data,
        'exceeded': total_spent > budget.amount if budget.amount > 0 else False
    }
    return render(request, 'dashboard.html', context)

@login_required
def add_expense(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            messages.success(request, "Expense added successfully!")
            return redirect('dashboard')
    else:
        form = ExpenseForm()
    return render(request, 'add_expense.html', {'form': form})

@login_required
def expense_list(request):
    query = request.GET.get('q', '')
    category_filter = request.GET.get('category', '')

    expenses = Expense.objects.filter(user=request.user).order_by('-date')

    if query:
        from django.db.models import Q
        expenses = expenses.filter(
            Q(description__icontains=query) | 
            Q(category__icontains=query)
        )
    if category_filter:
        expenses = expenses.filter(category=category_filter)

    
    categories_with_selected = [
        (code, label, category_filter == code)
        for code, label in Expense.CATEGORY_CHOICES
    ]

    context = {
        'expenses': expenses,
        'query': query,
        'category_filter': category_filter,
        'categories_with_selected': categories_with_selected,
    }
    return render(request, 'expense_list.html', context)

@login_required
def edit_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated successfully.")
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'add_expense.html', {'form': form, 'edit_mode': True, 'expense': expense})

@login_required
def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, "Expense deleted.")
        return redirect('expense_list')
    return render(request, 'delete_confirm.html', {'expense': expense})

@login_required
def set_budget(request):
    current_month = datetime.now().month
    current_year = datetime.now().year
    budget, created = Budget.objects.get_or_create(
        user=request.user, 
        month=current_month, 
        year=current_year,
        defaults={'amount': 0}
    )
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, instance=budget)
        if form.is_valid():
            form.save()
            messages.success(request, "Budget updated successfully.")
            return redirect('dashboard')
    else:
        form = BudgetForm(instance=budget)
        
    return render(request, 'set_budget.html', {'form': form})

@login_required
def export_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="expenses.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Date', 'Category', 'Amount', 'Description'])
    
    expenses = Expense.objects.filter(user=request.user).order_by('-date')
    for e in expenses:
        writer.writerow([e.date, e.category, e.amount, e.description])
        
    return response

@login_required
def import_csv(request):
    if request.method == 'POST' and request.FILES.get('csv_file'):
        csv_file = request.FILES['csv_file']
        
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'This is not a csv file')
            return redirect('dashboard')

        file_data = csv_file.read().decode('utf-8').splitlines()
        reader = csv.reader(file_data)
        next(reader, None) # Skip header
        
        imported = 0
        for row in reader:
            if len(row) >= 4:
                try:
                    date = datetime.strptime(row[0], '%Y-%m-%d').date()
                    amount = float(row[2])
                    Expense.objects.create(
                        user=request.user,
                        date=date,
                        category=row[1],
                        amount=amount,
                        description=row[3]
                    )
                    imported += 1
                except Exception as e:
                    pass
        
        messages.success(request, f"Successfully imported {imported} expenses.")
        return redirect('expense_list')
        
    return render(request, 'import_csv.html')
