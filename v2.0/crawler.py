# coding=utf8
"""
关注画师爬虫
time: 2020-05-11
author: coder_sakura
"""
import json
import time
import re

from downer import Down
from logstr import log_str
from message import *
from thread_pool import *


class Crawler(object):
	def __init__(self):
		self.Downloader = Down()
		self.user_id = self.Downloader.client.user_id
		self.base_request = self.Downloader.baseRequest

		# 画师列表
		self.follw_url = "https://www.pixiv.net/ajax/user/{}/following".format(self.user_id)
		# 作品链接,存数据库
		self.artworks_url = "https://www.pixiv.net/artworks/{}"
		# 画师作品列表
		self.all_illust_url = "https://www.pixiv.net/ajax/user/{}/profile/all"
		self.file_manager = self.Downloader.file_manager
		self.db = self.Downloader.db
		self.class_name = self.__class__.__name__

	def get_page_users(self,offset):
		"""
		:params offset 偏移量,按照偏移量获得limit范围内的画师
		:return 接口数据中的画师数组
		"""
		params = {
			"offset":offset,
			"limit":100,
			"rest":"show",			
		}
		try:
			r = json.loads(self.base_request({"url":self.follw_url},params=params).text)
		except Exception as e:
			# 网络请求出错
			log_str(FOLLOW_PAGE_ERROR_INFO.foramt(self.class_name,offset,offset+100))
			return None
		else:
			# 未登录
			if r["message"] == UNLOGIN_TEXT:
				log_str(UNLOGIN_INFO.format(self.class_name))
				return UL_TEXT
				
			res = r['body']['users']
			return res

	def get_users(self):
		"""
		:return: 所有关注画师的uid,userName,latest_id(最新的pid)
		:[{"uid":uid,"userName":userName,"latest_id":latest_id},...]
		"""
		offset = 0
		users_info_list = []

		while True:
			u_list = self.get_page_users(offset)

			# 网络请求出错
			if u_list == None:
				continue

			# 未登录
			if u_list == UL_TEXT:
				break

			# 获取所有关注完毕
			if u_list == []:
				break

			for u in u_list:
				user_info = {}
				user_info["uid"] = int(u["userId"])
				# userName = re.sub('[\\\/:*?"<>|]','_',u["userName"])
				userName = re.sub(r'[\s\/:*?"<>|\\]','_',u["userName"])
				user_info["userName"] = userName

				if u["illusts"] == []:
					user_info["latest_id"] = -1
					log_str(FOLLOW_NO_ILLUSTS_INFO.format(self.class_name,u["userName"],u["userId"]))
					# 无作品不做动作
					continue	
				else:
					user_info["latest_id"] = int(u["illusts"][0]["illustId"])

				users_info_list.append(user_info)


			offset += 100

		return users_info_list

	def get_user_illust(self, u):
		"""
		:params u: 画师信息--字典
		:return user_illust_list: 画师信息包括:uid,userName,latest_id,path
		"""
		u["path"] = self.file_manager.mkdir_painter(u)
		illust_url = self.all_illust_url.format(u["uid"])
		try:
			u_json = json.loads(self.base_request({"url":illust_url}).text)["body"]
			i = u_json["illusts"]
			m = u_json["manga"]
			# 列表推导式合并取keys,转为list
			user_illust_list = list([dict(i) if len(m) == 0 else dict(i,**m)][0].keys())
		except Exception as e:
			log_str(FOLLOW_DATA_ERROR_INFO.format(self.class_name,e))
			return []
		else:
			return user_illust_list

	def thread_by_illust(self, *args):
		"""
		线程任务函数
		"""
		pid = args[0]
		try:
			info = self.Downloader.get_illust_info(pid)
		except Exception as e:
			log_str(ILLUST_NETWORK_ERROR_INFO.format(self.class_name,pid,e))
			return 

		if info == None:
			log_str(ILLUST_EMPTY_INFO.format(self.class_name,pid))
			return

		# 数据库开关关闭
		if hasattr(self.db,"pool") == False:
			return 

		isExists,path = self.db.check_illust(pid)
		# 数据库无该记录
		if isExists == False:
			res = self.db.insert_illust(info)
			if res == False:
				log_str(INSERT_FAIL_INFO.format(self.class_name,pid))
			else:
				log_str(INSERT_SUCCESS_INFO.format(self.class_name,pid))
		# 数据库有该记录
		else:
			self.db.updata_illust(info)

	def run(self):
		log_str(BEGIN_INFO.format(self.class_name))
		try:
			u_list = self.get_users()
		except Exception as e:
			print(e)
			log_str(FOLLOW_ERROR_INFO.format(self.class_name))
			log_str(SLEEP_INFO.format(self.class_name))
			return
		else:
			log_str(FOLLOW_SUCCESS_INFO.format(self.class_name,len(u_list)))

		try:
			pool = ThreadPool(8)
			for i,u in enumerate(u_list):
				all_illust = self.get_user_illust(u)
				if hasattr(self.db,"pool"):
					latest_id = self.db.check_user(u)
					d_total = self.db.get_total(u)
				else:
					latest_id,d_total = 0,0

				position = "({}/{})".format(i+1,len(u_list))
				if u["latest_id"] >= latest_id and d_total < len(all_illust):
					# 满足条件更新
					log_str(UPDATE_USER_INFO.format(position,self.class_name,u["userName"],u["uid"],len(all_illust),u["latest_id"]))
					if hasattr(self.db,"pool"):
						self.db.update_latest_id(u)

					for pid in all_illust:
						pool.put(self.thread_by_illust,(pid,),callback)

					time.sleep(3)
				else:
					log_str(NOW_USER_INFO.format(position,self.class_name,u["userName"],u["uid"],len(all_illust)))
					continue

			pool.close()
		except Exception as e:
			log_str("Exception {}".format(e))
			pool.close()
		finally:
			pool.close()
		log_str(SLEEP_INFO.format(self.class_name))


# if __name__ == '__main__':
# 	from config import USERS_CYCLE
# 	c = Crawler()
# 	while True:
# 		c.run()
# 		time.sleep(USERS_CYCLE)