# -*- coding: utf-8 -*-
'''
Copyright 2015 
	Centre de données socio-politiques (CDSP)
	Fondation nationale des sciences politiques (FNSP)
	Centre national de la recherche scientifique (CNRS)
License
	This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>
'''


import logging, importlib, traceback
from threading import Lock, Thread
from zephserversettings import SERVICE_LIST


class ServiceManager(object):
	'''
		@sigleton
		class managing the services and their lifecycles.
		Due to some locks protecting memory, this class can be 
		a bottleneck if you want to manage a lot of services 
		in a small time

		A service lifecycle is inspired from Apache. It is first available, then it can be enabled

		If a service crashes the servicemanager, it will try to relaunch it (same object) in an other thread
	'''

	_instance = None
	_instance_lock = Lock()

	_manipulating_service_lock = Lock()

	_services_available = {}
	_services_enable = {}

	_pending_stop = False


	def __init__(self):
		'''
			private constructor, do not use it
		'''
		logging.info('Instatiating service_manager')
		pass


	@classmethod
	def get_instance(cls):
		'''
			singleton management
		'''
		if not cls._instance:
			cls._instance_lock.acquire()
			try:
				if not cls._instance:
					cls._instance = ServiceManager()
			finally:
				cls._instance_lock.release()
		return cls._instance

	
	def enable_service(self, service_name):
		'''
			Method enabling a service whitch is already avaiable

			Enabling a service means launching its threads (calling its main method)

			this method returns True if the service has been enabled, False otherwise
		'''
		if self._services_available.has_key(service_name) and not self._services_enable.has_key(service_name) and self._pending_stop == False:
			self._manipulating_service_lock.acquire()
			try:
				service = None
				if self._services_available.has_key(service_name) and not self._services_enable.has_key(service_name) and self._pending_stop == False:
					logging.debug('Enabling service %s', service_name)
					service = self._services_available[service_name]
					service.get_service_lock().acquire()
					if service.has_run():
						service.restart()
					else:
						service.start()
					service.get_service_lock().acquire()
			finally:
				if not service is None:
					service.get_service_lock().release()
				self._manipulating_service_lock.release()
				return True
		else:
			logging.warning('Failed enabling service %s', service_name)
			return False
			


	def enable_all_services(self):
		'''
			Method enabling all services available
		'''
		logging.debug('Enabling all services')
		output = True
		for service in self._services_available:
			if not self.enable_service(service):
				output = False
		logging.debug('Enabling all services... done')
		return output


	def disable_service(self, service_name):
		'''
			function disabling (killing threads) all services enabled
		'''
		logging.debug('Disabling %s', service_name)
		service = self._services_enable.get(service_name, None)
		if not service == None:
			service.disable()
			service.join()
			logging.debug('Disabling %s done', service_name)
			return True	
		else:
			logging.warning('Disabling %s fail', service_name)
			return False


	def disable_all_services(self):
		'''
			function deactivating all services.
			function returns True if all services have been launched, False otherwise
		'''
		logging.debug('Disabling all services')
		output = True
		services = self._services_enable.copy()
		for service in services:
			if not self.disable_service(service):
				output = False
		logging.debug('Disabling all services... done')
		return output



	def create_service(self, service_name, service_instance):
		'''
			function registering a service among all available in order to be launched
			function returns True if it has been registered, False if not
		'''
		logging.debug('Creating %s', service_name)
		if not self._services_available.has_key(service_name):
			self._manipulating_service_lock.acquire()
			if not self._services_available.has_key(service_name):
				self._services_available[service_name] = ServiceContainer(service_name,service_instance)
			self._manipulating_service_lock.release()
			logging.debug('Creating %s ... done', service_name)
			return True
		else:
			logging.warning('Creating %s ... fail', service_name)
			return False

	def create_all_service(self, enable_all=False):
		'''
			method instanciating dynamically all services in the variable named "SERVICE_LIST", in configs.py
		'''
		logging.info('Instanciating all services')
		for path in SERVICE_LIST:
			logging.debug('Importing service : %s', path)
			module = importlib.import_module(path.split('/')[0])
			class_def = getattr(module, path.split('/')[-1])()
			self.create_service(path, class_def)
		if enable_all:
			self.enable_all_services()

	def delete_service(self, service_name):
		'''
		function unsubscribing a service, rendering it unavailable
		function returns True if the service is found
		'''
		logging.debug('Deleting %s', service_name)
		if self._services_available.has_key(service_name):
			self._manipulating_service_lock.acquire()
			if self._services_available.has_key(service_name):
				del self._services_available[service_name]
			self._manipulating_service_lock.release()
			logging.debug('Deleting %s ... done', service_name)
			return True
		else:
			logging.warning('Deleting %s ... fail', service_name)
			return False


	def delete_all_services(self):
		'''
			funtion deleting all services
			function returns True if services has been deleted, False if not
		'''
		logging.debug('Deleting all services')
		output = True
		services = self._services_available.copy()
		for service in services:
			if not self.delete_service(service):
				output = False
		logging.debug('Deleting all services...done')
		return output


	def get_service(self, service_name):
		'''
			function returning the asked service if it exists and launching it if needed
			function returns None is service wasn't found
		'''
		logging.debug('Getting service %s',service_name)
		if self._services_enable.has_key(service_name):
			return self._services_enable[service_name].get_service()
		elif self._pending_stop == True:
			logging.warning('Service %s not found and stop pendding',service_name)
			return None
		elif self._services_available.has_key(service_name):
			if not self.enable_service(service_name):
				logging.warning('Service %s found but disable',service_name)
				return None
			return self._services_enable[service_name].get_service()
		else:
			logging.warning('Service %s not found !', service_name)
			return None

	def stop_service_manager(self):
		'''
			function stopping properly all services
		'''
		logging.info('Stopping service_manager')
		self._pending_stop = True
		self.disable_all_services()
		self.delete_all_services()
		self._instance_lock.acquire()
		self._instance = None
		self._instance_lock.release()
		self._pending_stop = False
		logging.info('Servicemanager has stopped')



class ServiceContainer(Thread):
	'''
		private class allowing you to manage more finely life cycles, re-creating itself in order to re-launch turned-off services
	'''
	_service_name = ''
	_service_instance = ''
	_service_lock = Lock()
	_has_run = False

	def __init__(self,service_name, service_instance):
		Thread.__init__(self)
		self._service_instance = service_instance
		self._service_name = service_name
		

	def run(self):
		ServiceManager.get_instance()._services_enable[self._service_name] = self
		self._service_lock.release()
		logging.debug('Success enabeling service %s', self._service_name)
		try:
			self._service_instance.main()
		except Exception, e:
			logging.error(e)
			logging.error(traceback.format_exc())

		finally:
			self._has_run = True
			ServiceManager.get_instance()._manipulating_service_lock.acquire()
			try:
				del ServiceManager.get_instance()._services_enable[self._service_name]
			finally:
				ServiceManager.get_instance()._manipulating_service_lock.release()

	def disable(self):
		'''
			transmit the death signal
		'''
		self._service_instance.disable()

	def get_service_lock(self):
		'''
			give the ServiceContainer's lock
		'''
		return self._service_lock


	def get_service(self):
		'''
			interface allowing you to leave no traces out of the service_manager
		'''
		return self._service_instance

	def has_run(self):
		'''
			encapsulation of the variable "self._has_run"
		'''
		return self._has_run

	def restart(self):
		'''
			method allowing you to ignore the "one start per thread"limitation, 
			re-creating a thread if a start is asked et the thread has already 
			started once

			this is a private method and should be called ONLY in your service 
			starting function "ServiceManager.enable_service", under penalty of 
			having undefined behaviors
		'''
		#_services_available
		service_manager = ServiceManager.get_instance()

		if service_manager._services_available.has_key(self._service_name):
			del service_manager._services_available[self._service_name]
		if service_manager._services_enable.has_key(self._service_name):
			del service_manager._services_enable[self._service_name]

		service_manager.create_service(self._service_name, self._service_instance)
		service_manager.enable_service(self._service_name)
		self._service_lock.release()
		