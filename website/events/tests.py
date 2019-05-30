from django.contrib.auth import get_user_model

from django.core import mail
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from events.admin import EventAdmin
from events.constants import (
    CANT_CHANGE_CLOSE_EVENT_MESSAGE,
    DUPLICATED_SPONSOR_CATEGORY_MESSAGE,
    MUST_BE_EVENT_ORGANIZAER_MESSAGE,
    ORGANIZER_MAIL_NOTOFICATION_MESSAGE
    )
from events.helpers.notifications import email_notifier
from events.helpers.tests import associate_users_permissions, CustomAssertMethods, organizer_permissions, super_organizer_permissions
from events.middleware import set_current_user
from events.models import Event, Organizer, EventOrganizer, SponsorCategory
from unittest.mock import patch, MagicMock

User = get_user_model()


class MockSuperUser:
    def has_perm(self, perm):
        return True

def associate_organizer_perms(organizers_users):
    permissions = organizer_permissions()
    associate_users_permissions(organizers_users, permissions)
    
def associate_super_organizer_perms(super_organizers_users):
    permissions = super_organizer_permissions()
    associate_users_permissions(super_organizers_users, permissions)

def create_user_set():
    """Create a organizer and superuser users."""
    organizers = []
    super_organizers=[]

    organizers.append(User.objects.create_user(username="organizer01", email="test01@test.com", password="organizer01"))
    organizers.append(User.objects.create_user(username="organizer02", email="test02@test.com", password="organizer02"))
    
    super_organizers.append(User.objects.create_user(username="superOrganizer01", email="super01@test.com", password="superOrganizer01"))
    # Created to test perms without use superuser.

    User.objects.create_superuser(
        username="administrator", 
        email="admin@test.com", 
        password="administrator"
        )

    associate_organizer_perms(organizers)
    associate_super_organizer_perms(super_organizers)

def create_event_set(user):
    """Create Events to test."""
    set_current_user(user)
    Event.objects.create(name='MyTest01', commission=10)
    Event.objects.create(name='MyTest02', commission=20)

def admin_event_associate_organizers_post_data(event, organizers):
    """Create data to send to events admin url to associate organizers to event."""
    data = {
        'name':[event.name], 
        'commission': [str(event.commission)], 
        'category': [''], 
        'start_date': [''], 
        'place': [''], 

        'event_organizers-TOTAL_FORMS': [str(len(organizers))], 
        'event_organizers-INITIAL_FORMS': ['0'], 
        'event_organizers-MIN_NUM_FORMS': ['0'], 
        'event_organizers-MAX_NUM_FORMS': ['1000'],
         
        'event_organizers-__prefix__-id': [''], 
        'event_organizers-__prefix__-event': ['1'], 
        'event_organizers-__prefix__-organizer': [''], 
        '_save': ['Save']
        }

    association_num = 0
    for organizer in organizers:
        prefix = f"event_organizers-{association_num}-"
        data[prefix + 'id']= ['']
        data[prefix + 'event']= [str(event.pk)] 
        data[prefix + 'organizer']= [str(organizer.pk)]
        association_num = association_num + 1

    return data


class EmailTest(TestCase, CustomAssertMethods):
    def setUp(self):
        create_user_set()
        user =User.objects.first()
        create_event_set(user)

    def test_send_email_after_register_organizer(self):
        # Login client with super user
        self.client.login(username='administrator', password='administrator')

        # Send request
        data = {
            'username':'juanito',
            'email':'new_organizer@pyar.com',
        }
        response = self.client.post(reverse('organizer_signup'), data=data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, render_to_string('mails/organizer_just_created_subject.txt'))

        self.assertContainsMessage(response, ORGANIZER_MAIL_NOTOFICATION_MESSAGE)


    def test_send_organizer_associated_to_event_sends_mails_with_subject(self):
        """ Testing that function 'send_organizer_associated_to_event' sends emails to the 
        listed organizers with the correct subject."""
        
        event = Event.objects.filter(name='MyTest01').first()
        Organizer.objects.bulk_create([
            Organizer(user=User.objects.get(username="organizer01"), first_name="Organizer01"),
            Organizer(user=User.objects.get(username="organizer02"), first_name="Organizer02")
        ])

        email_notifier.send_organizer_associated_to_event(event,Organizer.objects.all(),{'domain': 'testserver', 'protocol': 'http'})
        self.assertEqual(len(mail.outbox),2)

        send_to = []
        for email in mail.outbox:
            send_to.extend(email.to)
            self.assertEqual(email.subject, render_to_string('mails/organizer_associated_to_event_subject.txt'))
        
        self.assertIn('test01@test.com',send_to)
        self.assertIn('test02@test.com',send_to) 


class SingnupOrginizerTest(TestCase):
    def setUp(self):
        create_user_set()
    
    def test_organizer_signup_redirects_without_perms(self):
        response = self.client.get(reverse('organizer_signup'))
        # Login client with not superuser
        self.client.login(username='organizer01', password='organizer01')

        # View redirect.
        self.assertEqual(response.status_code, 302)
        
        # And redirect to login.
        redirect_to_login_url = reverse('login') + '?next=' + reverse('organizer_signup')
        self.assertEqual(response.url, redirect_to_login_url)

    def test_user_with_add_organizer_perm_no_redirects(self):
        # Login client with super_organizer
        self.client.login(username='superOrganizer01', password='superOrganizer01')

        response = self.client.get(reverse('organizer_signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'organizers/organizer_signup.html')

    def test_organizer_created_on_signup(self):
        self.client.login(username='superOrganizer01', password='superOrganizer01')
        url = reverse('organizer_signup')
        data = {
            'email':'test@mail.com',
            'username':'organizador_test'
        }
        response = self.client.post(url, data=data)
        self.assertTrue(Organizer.objects.filter(user=User.objects.get(username='organizador_test')).exists())        


class EventAdminTest(TestCase):
    def setUp(self):
        create_user_set()
        user = User.objects.first()
        create_event_set(user)

        Organizer.objects.bulk_create([
            Organizer(user=User.objects.get(username="organizer01"), first_name="Organizer01"),
            Organizer(user=User.objects.get(username="organizer02"), first_name="Organizer02")
        ])

    @patch('events.helpers.notifications.EmailNotification.send_organizer_associated_to_event')
    def test_on_organizer_associate_to_event_call_mail_function(self, send_email_function):
        event = Event.objects.filter(name='MyTest01').first()

        url = reverse('admin:events_event_change', kwargs={'object_id': event.pk})
        self.client.login(username='administrator', password='administrator')
        
        organizers = [] 
        for organizer in Organizer.objects.all():
            organizers.append(organizer)

        data = admin_event_associate_organizers_post_data(event, organizers)
        response = self.client.post(url, data=data)
        #import pdb; pdb.set_trace()
        send_email_function.assert_called_once_with(event, organizers, {'domain': 'testserver', 'protocol': 'http'})


class EventViewsTest(TestCase, CustomAssertMethods):
    def setUp(self):
        create_user_set()
        user = User.objects.first()
        create_event_set(user)
        
        Organizer.objects.bulk_create([
            Organizer(user=User.objects.get(username="organizer01"), first_name="Organizer01"),
            Organizer(user=User.objects.get(username="organizer02"), first_name="Organizer02")
        ])
    
    def test_event_detail_redirects_no_associated_organizer(self):
        event = Event.objects.filter(name='MyTest01').first()
        url = reverse('event_detail', kwargs={'pk': event.pk})
        self.client.login(username='organizer01', password='organizer01')
        response = self.client.get(url)
        expected_url = reverse('event_list')
        self.assertRedirects(response, expected_url)
        self.assertContainsMessage(response, MUST_BE_EVENT_ORGANIZAER_MESSAGE)
        
    def test_event_change_redirects_on_closed_event(self):
        event = Event.objects.filter(name='MyTest01').first()
        EventOrganizer.objects.create(event=event, organizer=Organizer.objects.get(user__username='organizer01'))
        event.close = True
        event.save()
        
        url = reverse('event_change', kwargs={'pk': event.pk})
        self.client.login(username='organizer01', password='organizer01')
        response = self.client.get(url)
        
        expected_url = reverse('event_detail', kwargs={'pk': event.pk})
        self.assertRedirects(response, expected_url)
        self.assertContainsMessage(response, CANT_CHANGE_CLOSE_EVENT_MESSAGE)

    def test_cant_duplicate_sponsor_category(self):
        set_current_user(User.objects.filter(username='organizer01').first())
        event = Event.objects.filter(name='MyTest01').first()
        EventOrganizer.objects.create(event=event, organizer=Organizer.objects.get(user__username='organizer01'))
        SponsorCategory.objects.create(name='Oro',amount=10000, event=event)
        
        url = reverse('event_create_sponsor_category', kwargs={'pk': event.pk})
        data = {
            'name':'Oro',
            'amount': '10000'
        }
        self.client.login(username='organizer01', password='organizer01')
        response = self.client.post(url, data)
        expected_url = reverse('event_detail', kwargs={'pk': event.pk})
        self.assertRedirects(response, expected_url)
        self.assertContainsMessage(response, DUPLICATED_SPONSOR_CATEGORY_MESSAGE)
    
    def test_cant_create_sponsor_category_not_event_organizer(self):
        set_current_user(User.objects.filter(username='organizer01').first())
        event = Event.objects.filter(name='MyTest01').first()
        url = reverse('event_create_sponsor_category', kwargs={'pk': event.pk})
        data = {
            'name':'Oro',
            'amount': '10000'
        }
        self.client.login(username='organizer01', password='organizer01')
        response = self.client.post(url, data)
        self.assertContainsMessage(response, MUST_BE_EVENT_ORGANIZAER_MESSAGE)
        self.assertFalse(SponsorCategory.objects.filter(name='Oro').exists())

    def test_create_sponsor_category_by_event_organizer(self):
        set_current_user(User.objects.filter(username='organizer01').first())
        event = Event.objects.filter(name='MyTest01').first()
        EventOrganizer.objects.create(event=event, organizer=Organizer.objects.get(user__username='organizer01'))
        url = reverse('event_create_sponsor_category', kwargs={'pk': event.pk})
        data = {
            'name':'Oro',
            'amount': '10000'
        }
        self.client.login(username='organizer01', password='organizer01')
        response = self.client.post(url, data)
        #self.assertContainsMessage(response, MUST_BE_EVENT_ORGANIZAER_MESSAGE)
        self.assertTrue(SponsorCategory.objects.filter(name='Oro').exists())

    def test_event_change_not_updating_name_and_commission(self):
        event = Event.objects.filter(name='MyTest01').first()
        EventOrganizer.objects.create(event=event, organizer=Organizer.objects.get(user__username='organizer01'))

        old_name = event.name
        old_commission = event.commission

        url = reverse('event_change', kwargs={'pk': event.pk})
        self.client.login(username='organizer01', password='organizer01')
        data = {
            'name':'noChange',
            'commission':'300',
            'place': 'Villa adelina'
        }
        response = self.client.post(url, data)
        expected_url = reverse('event_detail', kwargs={'pk': event.pk})
        self.assertRedirects(response, expected_url)
        event.refresh_from_db()
        self.assertEqual(event.name, old_name)
        self.assertEqual(event.commission, old_commission)
        self.assertEqual(event.place, 'Villa adelina')